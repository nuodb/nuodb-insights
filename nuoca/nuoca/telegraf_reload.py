import os, signal
from flask import Flask

app = Flask(__name__)


@app.route('/reload')
def reload():
    """ reload telegraf """
    ppid = os.getppid()
    if ppid:
        os.kill(ppid,signal.SIGHUP)
    return str(ppid)

if __name__ == '__main__':
    app.run()
