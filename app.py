from flask import Flask, url_for, render_template

from main import get_Table 
app = Flask(__name__)

OneZetHeight = 50;

@app.route('/')
def main():
    table = get_Table()
    return render_template("base.html", table=table, zet=OneZetHeight)



if __name__ == "__main__":
    app.run()