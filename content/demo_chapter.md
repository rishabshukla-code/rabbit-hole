# Set up your first Python web app

## 1. Create the project folder

Every project starts with its own folder. Open a terminal and make a new folder called `hello-web`, then move into it. Inside this folder we use a virtual environment for this project, so the packages we install stay separate from every other Python project on your computer. Create it with `python -m venv .venv` and activate it. You will see `(.venv)` at the start of your terminal line, which tells you it worked. We also run `git init` so the project is tracked by Git from the first minute, but you do not need to know Git well for this tutorial.

## 2. Install Flask

Flask is a small web framework: it turns Python functions into web pages. Install it with pip by running `pip install flask`. pip downloads Flask and the few packages Flask depends on and puts them inside your virtual environment. When it finishes, save the exact list of installed packages with `pip freeze > requirements.txt`. Anyone who gets your project later can recreate the same setup with one command, `pip install -r requirements.txt`. Some teams ship apps inside Docker containers instead, but we will not use Docker here.

## 3. Write your first route

Create a file called `app.py`. Import Flask, create an app object, and write one function that returns the text "Hello, web!". Above the function, add the decorator `@app.route("/")`. A decorator is a line starting with `@` that wraps the function below it; here it tells Flask to call your function when someone visits the home page. That function is your first route. Real apps also offer an API, a set of routes that return data such as JSON instead of pages, but one simple page is enough for today.

## 4. Run the app

Run `flask --app app run` in the terminal. Flask starts a small development server and prints an address like `http://127.0.0.1:5000`. The number at the end, 5000, is the port: think of it as a door number on your computer where the app is listening. Open that address in your browser and you will see "Hello, web!". Leave the terminal open while you test, because closing it stops the server.

## 5. Keep secrets out of your code

Apps often need secret values, like an API key for a payment service. Never type secrets directly into `app.py`. Put them in environment variables instead: values your operating system holds and your app reads when it starts. Many projects keep them in a `.env` file that is listed in `.gitignore`, so Git never uploads it. Read a value in Python with `os.environ.get("SECRET_KEY")`. You now have a working web app, a clean environment, and a safe place for secrets. That is the whole setup.
