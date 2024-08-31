
def logmessage(message: str = '', *, prefix: str = ''):
    print(f'{prefix} {message}')

def debug(message: str = '') :
    logmessage(message, prefix='DEBUG')

