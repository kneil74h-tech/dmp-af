def main(context, result=None):
    print("post hook", context.get("task_id"), "result=", result)
