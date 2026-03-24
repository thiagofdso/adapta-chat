import requests
import time

# --- CONFIGURAÇÕES ---
# Mantenha os cookies atualizados caso o script pare de funcionar
COOKIES = {
    '__client_uat_xcsZUTdN': '1763467077',
    'AMP_c78597472d': 'JTdCJTIyZGV2aWNlSWQlMjIlM0ElMjJjZjVmNDQwOC05ZjUyLTQ3YWQtOTY5Zi1iODI1YWQwYzQ1MjMlMjIlMkMlMjJ1c2VySWQlMjIlM0ElMjJ0aGlhZ29mZHNvLnVmcGElNDBnbWFpbC5jb20lMjIlMkMlMjJzZXNzaW9uSWQlMjIlM0ExNzYzNDcxNTQxNjgxJTJDJTIyb3B0T3V0JTIyJTNBZmFsc2UlMkMlMjJsYXN0RXZlbnRUaW1lJTIyJTNBMTc2MzQ3MTU0MTcyOCUyQyUyMmxhc3RFdmVudElkJTIyJTNBMTMlMkMlMjJwYWdlQ291bnRlciUyMiUzQTAlN0Q=',
    '_cfuvid': 'sPyP_N25Du7AY_76DYVv7VDSPj_Va4KaylmoV71Fn6Y-1774015906058-0.0.1.1-604800000',
    '__client': 'eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6ImNsaWVudF8zQXQyQkZvblFQRTVRdDcwTWJMRXJjM3pXWXQiLCJyb3RhdGluZ190b2tlbiI6IjN2ZGRsN3RkY3VnNmtqMGF1OGI0aWk2bHZ1NDBvcjd4bGxuYzBhZWcifQ.MEOERmOGeqMyRq4oUUnuvYsmVxvlDLmZWxSUw3Hd2aLPaw-T5ANpK3iYQNNYldJaY_p9mvgZF0PO6_N_3PONWKs_D7J0XOE_B-WBJpoBff0yShkmLqVv3I3pSskxpzqgUHyLOJdA-hYVegCQoqLoe4VwpyCrGkIto8jjJMQKGIiHqgVVy3KXvprFqWh7Ulyh7p-RzDTOXbse-hdIf4uB6gKgxJbg24MMdnJHnLrSpgEc5QVZAWheT9-30UfCNaS11t-A3r5x4HCtYXjp35e0zKePtCLoGvfQrbKIW4Uz3ruCzGOWGQ8aYCYx_l7TKJmmxwmyp5LNEsu3irH6zfKVbQ',
    '__client_uat': '1774276064',
    '__client_uat_0GUur0zr': '1774276064',
    '__cf_bm': 'F9Yk9r5NCiPxNgUAEZyFDsjCFrzXyp65JAG3mk6lzns-1774349118-1.0.1.1-HHwsIQmnNE.YjvF4wVeLo9WjDquxXb2Cn_d3kn_kwITm9n6VxbZbO5.N7G10x2RZiU.9O3vEbRHszAtzqCVE.VSO8aLBW1pqUZyeFDJfU9k',
    'ph_phc_EyNGMgUAq1JSXDq0JgLuO0MgIDlptaaKRQLwDvX8f7g_posthog': '%7B%22distinct_id%22%3A%22user_344fXQKSzbcTPa6s0K1oTrnY0yJ%22%2C%22%24sesid%22%3A%5B1774349186618%2C%22019d1f52-86fc-7125-a086-2a6fb4918d56%22%2C1774346995450%5D%2C%22%24epp%22%3Atrue%7D',
}

MAIN_SESSION_ID = "sess_3BLl7ZamJ6NLNFZogpuOrSGSjg6"

BASE_HEADERS = {
    'accept': '*/*',
    'accept-language': 'pt-BR,pt;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
    'origin': 'https://agent.adapta.one',
    'referer': 'https://agent.adapta.one/',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0',
}

def get_fresh_token():
    """Busca um novo JWT no Clerk para autorizar as chamadas de API"""
    url = f"https://clerk.agent.adapta.one/v1/client/sessions/{MAIN_SESSION_ID}/tokens"
    params = {'__clerk_api_version': '2025-11-10', '_clerk_js_version': '5.125.7'}
    data = {'organization_id': ''}
    
    headers = BASE_HEADERS.copy()
    headers['content-type'] = 'application/x-www-form-urlencoded'
    
    try:
        res = requests.post(url, headers=headers, cookies=COOKIES, params=params, data=data)
        if res.status_code == 200:
            return res.json().get('jwt')
        else:
            print(f"Erro ao obter token: {res.status_code}")
            return None
    except Exception as e:
        print(f"Falha na requisição de token: {e}")
        return None

def get_active_sessions():
    """Busca a lista de todas as sessões do usuário"""
    print("Obtendo lista de sessões ativas...")
    url = "https://clerk.agent.adapta.one/v1/me/sessions/active"
    params = {
        '__clerk_api_version': '2025-11-10',
        '_clerk_js_version': '5.125.7',
        '_clerk_session_id': MAIN_SESSION_ID
    }
    res = requests.get(url, headers=BASE_HEADERS, cookies=COOKIES, params=params)
    return res.json() if res.status_code == 200 else []

def fix_session(session_id, jwt_token):
    """Executa a correção da sessão no endpoint do agente"""
    url = "https://agent.adapta.one/api/user/fix-session/v1"
    headers = BASE_HEADERS.copy()
    headers['authorization'] = f'Bearer {jwt_token}'
    headers['content-type'] = 'application/json'
    
    payload = {"sessionId": session_id}
    try:
        res = requests.post(url, headers=headers, cookies=COOKIES, json=payload)
        return res.status_code
    except Exception as e:
        return f"Erro: {e}"

def main():
    # 1. Pega a lista inicial de sessões
    sessions = get_active_sessions()
    if not sessions:
        print("Nenhuma sessão encontrada ou erro nos cookies.")
        return

    total = len(sessions)
    print(f"Total de sessões encontradas: {total}")

    # 2. Inicializa o primeiro token

    # 3. Loop de processamento com renovação a cada 10 chamadas
    for index, session_info in enumerate(sessions, start=1):
        sid = session_info.get('id')
        

        if sid:
            print(f"[{index}/{total}] Sessão: {sid}")
            

    print("\nProcessamento concluído.")

if __name__ == "__main__":
    main()
