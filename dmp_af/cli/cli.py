import importlib.util
import os
from datetime import datetime
import subprocess
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, TemplateNotFound
from typing import Optional
import re

import click
import dotenv


class CLIException(Exception):
    """Base CLI exception."""
    def __init__(self, message: Optional[str] = None) -> None:
        super().__init__(message)


def find_repo_root(start_path: Path = None) -> Path:
    """Find the root directory of a Git repository.

    This function searches for a `.git` directory by moving upwards from the
    starting path until either:
    1. A `.git` directory is found (returns the containing directory)
    2. The filesystem root is reached (returns the original working directory)

    Args:
        start_path: Path to start searching from. If None, uses current
                   working directory.

    Returns:
        Path: The root directory of the Git repository if found,
              otherwise the current working directory.
    """
    if start_path is None:
        start_path = Path.cwd()

    current = start_path.resolve()

    while current != current.parent:
        if (current / '.git').exists():
            return current
        current = current.parent

    return Path.cwd()


def run_dbt_command(command, args=None):
    """Run a DBT command with common arguments and real-time output."""
    cmd = ['dbt', command] + (args or [])

    click.echo(f"🚀  Running: dbt {command}")

    try:
        result = subprocess.run(
            cmd,
            check=True
        )
        click.echo(f"✅  Command completed: dbt {command}")
        return result

    except subprocess.CalledProcessError as e:
        click.echo(f"❌  Command failed with exit code {e.returncode}: dbt {command}")
        if e.stderr:
            click.echo(f"Error: {e.stderr}")
        raise click.Abort()


def render_template_file(jinja_env: Environment, template_path: Path, output_path: Path, context: dict) -> None:
    """Render a template file using Jinja2 and save to output path.

    Args:
        jinja_env: The Jinja environment to use.
        template_path: Path to template file directory
        output_path: Path where to save rendered result
        context: Dictionary with variables for template

    Returns:
        bool: True if successful, False otherwise
    """
    if output_path.exists():
        return

    if not jinja_env:
        raise CLIException(
            f"Can't initialize Jinja environment. Specify `DMP_AF_CLI_TEMPLATES_FOLDER` environment variable and "
            f"create templates folder in your project according to CLI docs."
        )

    try:
        template_name = f"{template_path.parent.name}/{template_path.name}"
        template = jinja_env.get_template(template_name)
        rendered_content = template.render(**context)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered_content, encoding='utf-8')

        file_type = output_path.suffix[1:].upper()
        click.echo(f"📄 Created {file_type} file: {output_path}")
    except TemplateNotFound:
        return


class CustomCLI(click.Group):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._load_custom_commands()

    def _load_custom_commands(self):
        """Load custom commands from file specified in ENV or default location."""
        dotenv.load_dotenv()
        custom_commands_file = os.environ.get('DMP_AF_CLI_COMMANDS_FILE', None)

        if custom_commands_file:
            click.echo(message=f"📁 Found custom cli commands file path: {custom_commands_file}.", err=True)
        else:
            return

        file_path = os.path.join(os.getcwd(), custom_commands_file)

        if os.path.exists(file_path):
            try:
                spec = importlib.util.spec_from_file_location("custom_commands", file_path)
                if spec is None:
                    click.echo(f"❌ Can't create spec for file: {file_path}", err=True)
                    return

                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                click.echo(f"✅ Custom command module loaded: {file_path}", err=True)
            except SyntaxError as e:
                click.echo(f"❌ Syntax error in file {file_path}: {str(e)}", err=True)
                return
            except ImportError as e:
                click.echo(f"❌ Import error in file {file_path}: {str(e)}", err=True)
                return
            except PermissionError as e:
                click.echo(f"❌ Permission denied for file {file_path}: {str(e)}", err=True)
                return
            except Exception as e:
                click.echo(f"❌ Unexpected error for file {file_path}: {str(e)}", err=True)
                return

            commands_loaded_cnt = 0
            loaded_commands = set()
            for attr_name in dir(module):
                try:
                    if attr_name.startswith('_'):
                        continue

                    attr = getattr(module, attr_name)

                    if isinstance(attr, click.Command):
                        if not attr.name:
                            click.echo(message=f"⚠️ Skipped command without name: {attr_name}", err=True)
                            continue

                        if attr.name in loaded_commands:
                            click.echo(message=f"⚠️ Skipped command with duplicate name: {attr_name}", err=True)
                            continue

                        self.add_command(attr)
                        commands_loaded_cnt += 1
                        loaded_commands.add(attr_name)

                except Exception as e:
                    click.echo(f"⚠️ Exception while processing command {attr_name}: {e}", err=True)
                    continue

            if commands_loaded_cnt == 0:
                click.echo(message=f"💡 There are no commands found in file {file_path}.", err=True)
            else:
                click.echo(f"✅ Loaded {commands_loaded_cnt} custom commands: {', '.join(loaded_commands)}", err=True)


@click.group(cls=CustomCLI)
@click.version_option()
@click.pass_context
def cli(ctx):
    """Main CLI entrypoint with standard context."""
    ctx.ensure_object(dict)
    ctx.obj["start_time"] = datetime.now()
    ctx.obj["root_dir"] = find_repo_root()
    template_folder = os.getenv("DMP_AF_CLI_TEMPLATES_FOLDER")
    ctx.obj["templates_path"] = template_folder or ""
    ctx.obj["jinja_env"] = Environment(
        loader=FileSystemLoader(template_folder),
        trim_blocks=True,
        lstrip_blocks=True
    ) if template_folder else None


@cli.command(name="create-model")
@click.pass_context
@click.argument('model')
@click.option('--etl-service', '-e', required=True, help='ETL service (Airflow) name.', type=click.STRING)
@click.option('--domain', '-d', required=True, help='Model domain name.', type=click.STRING)
@click.option('--layer', '-l', required=True, help='Model layer name.', type=click.STRING)
@click.option('--storage', '-s', required=True, help='Model layer name.', type=click.STRING)
@click.option('--type', '-t', required=True, help='Model type name.', type=click.STRING)
def create_model(ctx, model: str, etl_service: str, domain: str, layer: str, storage: str, type: str):
    """Create a new DBT model with standardized structure.

    This command generates the necessary files for a DBT model following
    the project's naming conventions and directory structure.
    """
    base_dir = ctx.obj["root_dir"] / f"{etl_service}/dbt/models/{domain}/{storage}/{layer}/{model}"
    model_name = f"{domain}.{layer}.{model}"

    template_context = {
        'model': model,
        'model_name': model_name,
        'etl_service': etl_service,
        'domain': domain,
        'layer': layer,
        'storage': storage,
    }

    rendered_files = [
        {
            "template_path": Path(ctx.obj["templates_path"]) / type / f"{type}.sql",
            "output_path": base_dir / f"{model_name}.sql",
        },
        {
            "template_path": Path(ctx.obj["templates_path"]) / type / f"{type}.py",
            "output_path": base_dir / f"{model_name}.py",
        },
        {
            "template_path": Path(ctx.obj["templates_path"]) / type / f"{type}.yaml",
            "output_path": base_dir / f"{model_name}.yaml",
        },
    ]

    for rendered_file in rendered_files:
        render_template_file(
            jinja_env=ctx.obj["jinja_env"],
            template_path=rendered_file["template_path"],
            output_path=rendered_file["output_path"],
            context=template_context
        )


@cli.command(name="dbt-build")
@click.option('--compile', '-c', 'compile_flg', is_flag=True, help='Compile DBT project after parsing.')
@click.option('--docs', '-d', 'docs_flg', is_flag=True, help='Generate documentation.')
@click.option('--no-deps', '-nd', 'no_deps_flg', is_flag=True, help='Skip dependencies installation.')
@click.option('--target', '-t', default=lambda: os.environ.get('DBT_TARGET', 'dev'), type=click.STRING,
              help='DBT target environment.')
@click.option('--debug', is_flag=True, help='Enable debug output for DBT commands.')
@click.pass_context
def dbt_build(ctx, compile_flg, docs_flg, no_deps_flg, target, debug):
    """Build DBT project."""

    common_args = [
        '--profiles-dir', ctx.obj["root_dir"],
        '--project-dir', ctx.obj["root_dir"],
        '--target', target
    ]

    if debug:
        common_args.insert(0, '--debug')

    commands = [
        ('clean', "🧹  Cleaning project...", common_args),
        ('deps', "📦  Installing dependencies...", common_args) if not no_deps_flg else None,
        ('parse', "🔍  Parsing project...", common_args),
        ('compile', "🛠️  Compiling project...", common_args) if compile_flg else None,
        ('docs', "📚  Generating documentation...",
         ["generate", "--no-compile", "--empty-catalog"] + common_args) if docs_flg else None,
    ]

    commands = [cmd for cmd in commands if cmd is not None]

    for command, message, extra_args in commands:
        click.echo(message)
        run_dbt_command(command, extra_args)

    click.echo("\n🎉  DBT build completed successfully!")

    actions_taken = []
    if not no_deps_flg:
        actions_taken.append("installed dependencies")
    if compile_flg:
        actions_taken.append("project compiled")
    if docs_flg:
        actions_taken.append("docs generated")

    if actions_taken:
        click.echo(f"🎯  Additional actions: {', '.join(actions_taken)}")


@cli.command(name="dbt-run")
@click.argument('model')
@click.option('--target', '-t', default=lambda: os.environ.get('DBT_TARGET', 'dev'), type=click.STRING,
              help='DBT target environment.')
@click.option('--start_dttm', '-t', default=lambda: os.environ.get('START_DTTM', 'dev'), type=click.STRING,
              help='DBT target environment.')
@click.option('--end_dttm', '-t', default=lambda: os.environ.get('END_DTTM', 'dev'), type=click.STRING,
              help='DBT target environment.')
@click.pass_context
def dbt_run(ctx, model, start_dttm, end_dttm, target):
    """Run DBT model."""

    common_args = [
        '--profiles-dir', ctx.obj["root_dir"],
        '--project-dir', ctx.obj["root_dir"],
        '--target', target
    ]

    click.echo("🚀  Running model...")

    run_dbt_command(
        command="run",
        args=["--select", model] + common_args +
             ["--vars", f'{{"start_dttm": "{start_dttm}", "end_dttm": "{end_dttm}", "overlap": False}}']
    )


@cli.command(name="dbt-test")
@click.argument('model')
@click.option('--target', '-t', default=lambda: os.environ.get('DBT_TARGET', 'dev'), type=click.STRING,
              help='DBT target environment.')
@click.option('--start_dttm', '-t', default=lambda: os.environ.get('START_DTTM', 'dev'), type=click.STRING,
              help='DBT target environment.')
@click.option('--end_dttm', '-t', default=lambda: os.environ.get('END_DTTM', 'dev'), type=click.STRING,
              help='DBT target environment.')
@click.pass_context
def dbt_run(ctx, model, start_dttm, end_dttm, target):
    """Run DBT model."""

    common_args = [
        '--profiles-dir', ctx.obj["root_dir"],
        '--project-dir', ctx.obj["root_dir"],
        '--target', target
    ]

    click.echo("🚀  Running model tests...")

    run_dbt_command(
        command="test",
        args=["--select", model] + common_args +
             ["--vars", f'{{"start_dttm": "{start_dttm}", "end_dttm": "{end_dttm}", "overlap": False}}']
    )


@cli.command(name="dbt-seed")
@click.argument('model')
@click.option('--target', '-t', default=lambda: os.environ.get('DBT_TARGET', 'dev'), type=click.STRING,
              help='DBT target environment.')
@click.option('--start_dttm', '-t', default=lambda: os.environ.get('START_DTTM', 'dev'), type=click.STRING,
              help='DBT target environment.')
@click.option('--end_dttm', '-t', default=lambda: os.environ.get('END_DTTM', 'dev'), type=click.STRING,
              help='DBT target environment.')
@click.pass_context
def dbt_run(ctx, model, start_dttm, end_dttm, target):
    """Run DBT model."""

    common_args = [
        '--profiles-dir', ctx.obj["root_dir"],
        '--project-dir', ctx.obj["root_dir"],
        '--target', target
    ]

    click.echo("🚀  Running model seeds...")

    run_dbt_command(
        command="seed",
        args=["--select", model] + common_args +
             ["--vars", f'{{"start_dttm": "{start_dttm}", "end_dttm": "{end_dttm}", "overlap": False}}']
    )


@cli.command(name="dbt-snapshot")
@click.argument('model')
@click.option('--target', '-t', default=lambda: os.environ.get('DBT_TARGET', 'dev'), type=click.STRING,
              help='DBT target environment.')
@click.option('--start_dttm', '-t', default=lambda: os.environ.get('START_DTTM', 'dev'), type=click.STRING,
              help='DBT target environment.')
@click.option('--end_dttm', '-t', default=lambda: os.environ.get('END_DTTM', 'dev'), type=click.STRING,
              help='DBT target environment.')
@click.pass_context
def dbt_run(ctx, model, start_dttm, end_dttm, target):
    """Run DBT model."""

    common_args = [
        '--profiles-dir', ctx.obj["root_dir"],
        '--project-dir', ctx.obj["root_dir"],
        '--target', target
    ]

    click.echo("🚀  Running model snapshots...")

    run_dbt_command(
        command="snapshot",
        args=["--select", model] + common_args +
             ["--vars", f'{{"start_dttm": "{start_dttm}", "end_dttm": "{end_dttm}", "overlap": False}}']
    )


@cli.command(name="create-etl-service")
@click.argument('service_name')
@click.option('--with-dags/--no-dags', default=True, help='Создавать папку dags (по умолчанию: да).')
@click.pass_context
def create_etl_service(ctx, service_name: str, with_dags: bool):
    """Create a new ETL service (Airflow).

    Creates the folder structure: <service_name>/, <service_name>/dbt/models, <service_name>/dbt/seeds
    and optionally <service_name>/dags. Also adds corresponding paths to the root dbt_project.yml
    under the following sections: model-paths, snapshot-paths, seed-paths, test-paths, analysis-paths
    and macro-paths. Existing entries are not duplicated.
    """
    root_dir: Path = ctx.obj.get("root_dir", Path.cwd())

    service_dir = root_dir / service_name
    dbt_models = service_dir / 'dbt' / 'models'
    dbt_seeds = service_dir / 'dbt' / 'seeds'
    dags_dir = service_dir /  'dags' / 'system'

    try:
        service_dir.mkdir(parents=True, exist_ok=True)
        (service_dir / '__init__.py').write_text("# package for {}\n".format(service_name), encoding='utf-8')
        dbt_models.mkdir(parents=True, exist_ok=True)
        dbt_seeds.mkdir(parents=True, exist_ok=True)
        if with_dags:
            dags_dir.mkdir(parents=True, exist_ok=True)
        click.echo(f"📁 Created ETL service folders for: {service_name}")
    except Exception as e:
        click.echo(f"❌ Failed to create folders for {service_name}: {e}")
        raise click.Abort()

    if with_dags:
        try:
            src = root_dir / 'template-etl' / 'dags' / 'dbt_dag.py'
            dest = dags_dir / 'dbt_dag.py'
            if dest.exists():
                click.echo(f"ℹ️ DAG file already exists, skipping: {dest}")
            elif not src.exists():
                click.echo(f"⚠️ Template DAG not found at {src}. Skipping DAG copy.")
            else:
                content = src.read_text(encoding='utf-8')
                template_context = {"etl_service": service_name}
                jinja_local = Environment()
                rendered = jinja_local.from_string(content).render(**template_context)
                dest.write_text(rendered, encoding='utf-8')
                click.echo(f"📄 Created DAG file: {dest}")
        except Exception as e:
            click.echo(f"❌ Failed to modify DAG for {service_name}: {e}")
            raise click.Abort()

    dbt_file = root_dir / 'dbt_project.yml'
    if not dbt_file.exists():
        click.echo(f"⚠️ dbt_project.yml not found at {dbt_file}. Skipping update.")
        return

    try:
        text = dbt_file.read_text(encoding='utf-8')
    except Exception as e:
        click.echo(f"❌ Can't read dbt_project.yml: {e}")
        raise click.Abort()

    def add_path_to_array(yaml_text: str, key: str, new_path: str):
        pattern = rf'({re.escape(key)}\s*:\s*\[)(.*?)(\])'
        m = re.search(pattern, yaml_text, flags=re.DOTALL)
        if m:
            inside = m.group(2)
            if new_path in inside:
                return yaml_text, False
            insertion = f"  \"{new_path}\",\n"
            new_inside = inside + insertion
            new_text = yaml_text[:m.start(1)] + m.group(1) + new_inside + m.group(3) + yaml_text[m.end(3):]
            return new_text, True
        else:
            append_block = f"\n{key}: [\n  \"{new_path}\",\n]\n"
            return yaml_text + append_block, True

    updates = []
    mapping = {
        'model-paths': f"{service_name}/dbt/models",
        'snapshot-paths': f"{service_name}/dbt/models",
        'seed-paths': f"{service_name}/dbt/seeds",
        'test-paths': f"{service_name}/dbt/tests",
        'analysis-paths': f"{service_name}/dbt/analysis",
        'macro-paths': f"{service_name}/dbt/macros",
    }

    new_text = text
    for key, path_value in mapping.items():
        new_text, changed = add_path_to_array(new_text, key, path_value)
        if changed:
            updates.append((key, path_value))

    if updates:
        try:
            dbt_file.write_text(new_text, encoding='utf-8')
            click.echo(f"✅ Updated dbt_project.yml: added {len(updates)} path(s)")
            for k, p in updates:
                click.echo(f"  - {k}: {p}")
        except Exception as e:
            click.echo(f"❌ Can't write dbt_project.yml: {e}")
            raise click.Abort()
    else:
        click.echo("ℹ️ dbt_project.yml already contains paths for this service. No changes made.")


if __name__ == '__main__':
    cli()