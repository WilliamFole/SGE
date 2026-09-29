import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database import init_db
from app import app


def run_tests():
    init_db()  # sem isto, a app corre contra uma base de dados vazia (sem tabelas)
    with app.test_client() as c:
        # login (admin default from init_db)
        r = c.post('/login', data={'login': 'admin', 'senha': 'admin123'}, follow_redirects=True)
        print('LOGIN ->', r.status_code)

        endpoints = ['/balancetes', '/estoque', '/estoque/inventario', '/movimentos/entrada']
        for ep in endpoints:
            rr = c.get(ep)
            text = rr.data.decode('utf-8', 'ignore')[:400].replace('\n', ' ')
            print(f"{ep} -> {rr.status_code} | {text[:300]}")


if __name__ == '__main__':
    run_tests()
