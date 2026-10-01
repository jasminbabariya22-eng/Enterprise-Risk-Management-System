from flask import Flask
from app import create_app
#print("HELLO DEBUG5111")
#app = Flask(__name__)
app = create_app()

if __name__ == "__main__":
    app.run(host='0.0.0.0',port=8088,debug=True, use_reloader=False)