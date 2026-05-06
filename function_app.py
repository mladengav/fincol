import azure.functions as func

app = func.FunctionApp()

@app.route("hello")
def http_trigger(req):
    user = req.params.get("user")
    return f"Hello, {user}!"