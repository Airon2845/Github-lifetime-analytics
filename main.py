from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.responses import HTMLResponse
import requests
from datetime import datetime
import sqlite3
import secrets
import os

app = FastAPI(title="GitHub Analytics")
DATABASE_PATH = "github_analytics.db"

# ==================== БАЗА ДАННЫХ ====================
def init_db():
    if os.path.exists(DATABASE_PATH):
        os.remove(DATABASE_PATH)
    
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    cursor.executescript('''
        CREATE TABLE user_tokens (
            session_id TEXT UNIQUE NOT NULL,
            github_token TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE tracked_repos (
            session_id TEXT NOT NULL,
            owner TEXT NOT NULL,
            repo_name TEXT NOT NULL,
            UNIQUE(session_id, owner, repo_name)
        );
        
        CREATE TABLE repo_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner TEXT NOT NULL,
            repo_name TEXT NOT NULL,
            date DATE NOT NULL,
            views INTEGER DEFAULT 0,
            unique_visitors INTEGER DEFAULT 0,
            clones INTEGER DEFAULT 0,
            unique_clones INTEGER DEFAULT 0,
            stars INTEGER DEFAULT 0,
            forks INTEGER DEFAULT 0,
            collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(owner, repo_name, date)
        );
    ''')
    
    conn.commit()
    conn.close()
    print("✅ База пересоздана с правильной структурой")

init_db()

def save_token(session_id, token):
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO user_tokens (session_id, github_token) VALUES (?, ?)', (session_id, token))
    conn.commit()
    conn.close()

def get_token(session_id):
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT github_token FROM user_tokens WHERE session_id = ?', (session_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def add_tracked_repo(session_id, owner, repo):
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO tracked_repos VALUES (?, ?, ?)', (session_id, owner, repo))
    conn.commit()
    conn.close()

def get_tracked_repos(session_id):
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT owner, repo_name FROM tracked_repos WHERE session_id = ?', (session_id,))
    repos = cursor.fetchall()
    conn.close()
    return [{"owner": r[0], "name": r[1]} for r in repos]

def save_stats(owner, repo, stats):
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO repo_stats 
        (owner, repo_name, date, views, unique_visitors, clones, unique_clones, stars, forks)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        owner, repo, datetime.now().date(),
        stats['views'], stats['unique_visitors'],
        stats['clones'], stats['unique_clones'],
        stats['stars'], stats['forks']
    ))
    conn.commit()
    conn.close()

# ==================== GITHUB API ====================
def get_github_stats(owner, repo, token):
    headers = {'Authorization': f'token {token}', 'Accept': 'application/vnd.github.v3+json'}
    base_url = f"https://api.github.com/repos/{owner}/{repo}"
    
    try:
        response = requests.get(base_url, headers=headers)
        if response.status_code != 200:
            return {"success": False, "error": f"API error: {response.status_code}"}
        repo_data = response.json()
        
        views_response = requests.get(f"{base_url}/traffic/views", headers=headers)
        views_data = views_response.json() if views_response.status_code == 200 else {'count': 0, 'uniques': 0}
        
        clones_response = requests.get(f"{base_url}/traffic/clones", headers=headers)
        clones_data = clones_response.json() if clones_response.status_code == 200 else {'count': 0, 'uniques': 0}
        
        return {
            "success": True,
            "data": {
                "owner": owner,
                "repo_name": repo,
                "stars": repo_data.get('stargazers_count', 0),
                "forks": repo_data.get('forks_count', 0),
                "views": views_data.get('count', 0),
                "unique_visitors": views_data.get('uniques', 0),
                "clones": clones_data.get('count', 0),
                "unique_clones": clones_data.get('uniques', 0),
                "collected_at": datetime.now().isoformat()
            }
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

# ==================== АВТО-СБОР ====================
def auto_collect():
    """Собирает статистику для всех отслеживаемых репозиториев"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT DISTINCT tr.owner, tr.repo_name, ut.github_token 
        FROM tracked_repos tr
        JOIN user_tokens ut ON tr.session_id = ut.session_id
    ''')
    
    repos = cursor.fetchall()
    conn.close()
    
    print(f"🤖 Авто-сбор: {len(repos)} репозиториев")
    
    for owner, repo, token in repos:
        try:
            stats = get_github_stats(owner, repo, token)
            if stats["success"]:
                save_stats(owner, repo, stats["data"])
                print(f"✅ {owner}/{repo}")
        except Exception as e:
            print(f"❌ {owner}/{repo}: {e}")

# ==================== ВЕБ-ИНТЕРФЕЙС ====================
HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>GitHub Analytics</title>
    <style>
        body { font-family: Arial; max-width: 800px; margin: 0 auto; padding: 20px; }
        .container { background: #f5f5f5; padding: 20px; border-radius: 10px; margin: 10px 0; }
        input, button { padding: 10px; margin: 5px; width: 300px; }
        button { background: #007acc; color: white; border: none; cursor: pointer; }
        .message { padding: 10px; margin: 10px 0; border-radius: 5px; }
        .success { background: #d4edda; color: #155724; }
        .error { background: #f8d7da; color: #721c24; }
        .repo { background: white; padding: 10px; margin: 5px 0; border-radius: 5px; }
    </style>
</head>
<body>
    <h1>🚀 GitHub Analytics + Авто-сбор</h1>
    
    <div class="container">
        <h2>1. Сохранить токен</h2>
        <form action="/token" method="post">
            <input type="password" name="token" placeholder="ghp_твой_токен" required>
            <button>Сохранить</button>
        </form>
    </div>

    <div class="container">
        <h2>2. Добавить репозиторий для авто-слежения</h2>
        <form action="/track" method="post">
            <input type="text" name="owner" placeholder="Владелец" required>
            <input type="text" name="repo" placeholder="Репозиторий" required>
            <button>➕ Добавить</button>
        </form>
    </div>

    <div class="container">
        <h2>3. Собрать статистику сейчас</h2>
        <form id="statsForm">
            <input type="text" id="owner" placeholder="Владелец" required>
            <input type="text" id="repo" placeholder="Репозиторий" required>
            <button type="submit">📊 Собрать</button>
        </form>
    </div>

    <div class="container">
        <h2>📦 Отслеживаемые репозитории</h2>
        <div id="reposList">Загрузка...</div>
    </div>

    <div class="container">
        <h2>🤖 Авто-сбор</h2>
        <p>Данные собираются автоматически каждый день</p>
        <button onclick="runAutoCollect()">Запустить сейчас</button>
    </div>

    <div id="result"></div>

    <script>
        // Загрузить список репозиториев
        async function loadRepos() {
            const response = await fetch('/tracked');
            const data = await response.json();
            document.getElementById('reposList').innerHTML = 
                data.repos.map(r => `<div class="repo">📦 ${r.owner}/${r.name}</div>`).join('') || 'Нет репозиториев';
        }

        // Сбор статистики
        document.getElementById('statsForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const owner = document.getElementById('owner').value;
            const repo = document.getElementById('repo').value;
            
            try {
                const response = await fetch(`/stats/${owner}/${repo}`, {method: 'POST'});
                const data = await response.json();
                
                if (response.ok) {
                    document.getElementById('result').innerHTML = `
                        <div class="message success">
                            <h3>✅ ${data.message}</h3>
                            <p>⭐ Звезды: ${data.data.stars}</p>
                            <p>👀 Просмотры: ${data.data.views}</p>
                            <p>💾 Клоны: ${data.data.clones}</p>
                            <p>🍴 Форки: ${data.data.forks}</p>
                        </div>
                    `;
                    loadRepos();
                } else {
                    document.getElementById('result').innerHTML = `<div class="message error">❌ ${data.detail}</div>`;
                }
            } catch (error) {
                document.getElementById('result').innerHTML = '<div class="message error">❌ Ошибка</div>';
            }
        });

        // Авто-сбор
        async function runAutoCollect() {
            const response = await fetch('/auto-collect', {method: 'POST'});
            const data = await response.json();
            alert(data.message);
        }

        loadRepos();
    </script>
</body>
</html>
"""

# ==================== API ====================
@app.get("/")
async def root():
    return HTMLResponse(HTML)

@app.post("/token")
async def set_token(request: Request, token: str = Form(...)):
    session_id = request.cookies.get("session_id") or secrets.token_hex(16)
    save_token(session_id, token)
    response = HTMLResponse("✅ Токен сохранен! <a href='/'>Назад</a>")
    response.set_cookie(key="session_id", value=session_id)
    return response

@app.post("/track")
async def track_repo(request: Request, owner: str = Form(...), repo: str = Form(...)):
    session_id = request.cookies.get("session_id")
    if not session_id:
        raise HTTPException(400, "Сначала сохраните токен")
    
    add_tracked_repo(session_id, owner, repo)
    
    token = get_token(session_id)
    if token:
        stats = get_github_stats(owner, repo, token)
        if stats["success"]:
            save_stats(owner, repo, stats["data"])
    
    return HTMLResponse(f"✅ {owner}/{repo} добавлен! <a href='/'>Назад</a>")

@app.post("/stats/{owner}/{repo}")
async def collect_stats(owner: str, repo: str, request: Request):
    session_id = request.cookies.get("session_id")
    token = get_token(session_id) if session_id else None
    
    if not token:
        raise HTTPException(400, "Сначала сохраните токен")
    
    stats = get_github_stats(owner, repo, token)
    if not stats["success"]:
        raise HTTPException(400, stats["error"])
    
    save_stats(owner, repo, stats["data"])
    return {"message": "Статистика собрана!", "data": stats["data"]}

@app.get("/tracked")
async def get_tracked(request: Request):
    session_id = request.cookies.get("session_id")
    repos = get_tracked_repos(session_id) if session_id else []
    return {"repos": repos}

@app.post("/auto-collect")
async def run_auto_collect():
    auto_collect()
    return {"message": "Авто-сбор завершен!"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)