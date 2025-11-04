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
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GitHub Analytics Dashboard</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        :root {
            --primary: #2ea44f;
            --primary-dark: #2c974b;
            --secondary: #0366d6;
            --dark: #24292e;
            --light: #f6f8fa;
            --border: #e1e4e8;
            --text: #24292e;
            --text-light: #586069;
            --success: #28a745;
            --warning: #ffc107;
            --danger: #dc3545;
            --card-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
            --transition: all 0.3s ease;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            color: var(--text);
            line-height: 1.6;
            min-height: 100vh;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }

        /* Header */
        header {
            background: var(--dark);
            color: white;
            padding: 1rem 0;
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
        }

        .header-content {
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .logo {
            display: flex;
            align-items: center;
            gap: 10px;
            font-size: 1.5rem;
            font-weight: 700;
        }

        .logo i {
            color: var(--primary);
        }

        /* Main Layout */
        .dashboard {
            display: grid;
            grid-template-columns: 1fr 300px;
            gap: 24px;
            margin-top: 24px;
        }

        @media (max-width: 768px) {
            .dashboard {
                grid-template-columns: 1fr;
            }
        }

        /* Cards */
        .card {
            background: white;
            border-radius: 12px;
            padding: 24px;
            box-shadow: var(--card-shadow);
            margin-bottom: 24px;
            transition: var(--transition);
            border: 1px solid var(--border);
        }

        .card:hover {
            transform: translateY(-5px);
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
        }

        .card-header {
            display: flex;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 12px;
            border-bottom: 1px solid var(--border);
        }

        .card-header i {
            margin-right: 10px;
            color: var(--primary);
            font-size: 1.2rem;
        }

        .card-title {
            font-size: 1.25rem;
            font-weight: 600;
        }

        /* Forms */
        .form-group {
            margin-bottom: 16px;
        }

        .form-label {
            display: block;
            margin-bottom: 6px;
            font-weight: 500;
            color: var(--text-light);
        }

        .form-input {
            width: 100%;
            padding: 12px 16px;
            border: 1px solid var(--border);
            border-radius: 8px;
            font-size: 1rem;
            transition: var(--transition);
        }

        .form-input:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(46, 164, 79, 0.2);
        }

        .form-row {
            display: flex;
            gap: 12px;
        }

        .form-row .form-group {
            flex: 1;
        }

        /* Buttons */
        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            padding: 12px 20px;
            border: none;
            border-radius: 8px;
            font-size: 1rem;
            font-weight: 500;
            cursor: pointer;
            transition: var(--transition);
            text-decoration: none;
        }

        .btn-primary {
            background: var(--primary);
            color: white;
        }

        .btn-primary:hover {
            background: var(--primary-dark);
            transform: translateY(-2px);
        }

        .btn-secondary {
            background: var(--secondary);
            color: white;
        }

        .btn-secondary:hover {
            background: #0256b3;
            transform: translateY(-2px);
        }

        .btn-block {
            width: 100%;
        }

        .btn-sm {
            padding: 8px 12px;
            font-size: 0.875rem;
        }

        /* Stats Grid */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 16px;
            margin-top: 16px;
        }

        .stat-card {
            background: var(--light);
            border-radius: 8px;
            padding: 16px;
            text-align: center;
            border-left: 4px solid var(--primary);
        }

        .stat-value {
            font-size: 1.75rem;
            font-weight: 700;
            color: var(--dark);
            margin: 8px 0;
        }

        .stat-label {
            font-size: 0.875rem;
            color: var(--text-light);
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 4px;
        }

        /* Repo Widgets */
        .repo-widgets {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }

        .repo-widget {
            background: white;
            border-radius: 12px;
            padding: 20px;
            box-shadow: var(--card-shadow);
            border: 2px solid var(--border);
            transition: var(--transition);
            position: relative;
        }

        .repo-widget:hover {
            transform: translateY(-3px);
            box-shadow: 0 6px 20px rgba(0, 0, 0, 0.15);
            border-color: var(--primary);
        }

        .repo-widget-header {
            display: flex;
            justify-content: between;
            align-items: flex-start;
            margin-bottom: 16px;
        }

        .repo-widget-info {
            flex: 1;
        }

        .repo-widget-name {
            font-size: 1.1rem;
            font-weight: 600;
            color: var(--dark);
            margin-bottom: 4px;
        }

        .repo-widget-owner {
            color: var(--text-light);
            font-size: 0.9rem;
        }

        .repo-widget-actions {
            display: flex;
            gap: 8px;
        }

        .repo-widget-stats {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 12px;
            margin-top: 12px;
        }

        .repo-stat {
            text-align: center;
            padding: 8px;
            background: var(--light);
            border-radius: 6px;
        }

        .repo-stat-value {
            font-size: 1.2rem;
            font-weight: 700;
            color: var(--dark);
        }

        .repo-stat-label {
            font-size: 0.75rem;
            color: var(--text-light);
            margin-top: 4px;
        }

        .repo-widget-updated {
            font-size: 0.75rem;
            color: var(--text-light);
            margin-top: 12px;
            text-align: center;
        }

        .refresh-btn {
            background: transparent;
            border: none;
            color: var(--text-light);
            cursor: pointer;
            padding: 4px;
            border-radius: 4px;
            transition: var(--transition);
        }

        .refresh-btn:hover {
            color: var(--primary);
            background: var(--light);
        }

        .loading .repo-stat-value {
            color: transparent;
            background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
            background-size: 200% 100%;
            animation: loading 1.5s infinite;
            border-radius: 4px;
        }

        @keyframes loading {
            0% { background-position: 200% 0; }
            100% { background-position: -200% 0; }
        }

        /* Messages */
        .message {
            padding: 16px;
            border-radius: 8px;
            margin: 16px 0;
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .message-success {
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }

        .message-error {
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }

        /* Loading */
        .loading {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid rgba(255,255,255,.3);
            border-radius: 50%;
            border-top-color: #fff;
            animation: spin 1s ease-in-out infinite;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        /* Auto Collect Section */
        .auto-collect {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            text-align: center;
        }

        .auto-collect .card-title {
            color: white;
        }

        .auto-collect .btn {
            background: rgba(255,255,255,0.2);
            color: white;
            border: 1px solid rgba(255,255,255,0.3);
        }

        .auto-collect .btn:hover {
            background: rgba(255,255,255,0.3);
        }

        /* Footer */
        footer {
            text-align: center;
            margin-top: 40px;
            padding: 20px;
            color: var(--text-light);
            font-size: 0.875rem;
        }

        .empty-state {
            text-align: center;
            padding: 40px 20px;
            color: var(--text-light);
        }

        .empty-state i {
            font-size: 3rem;
            margin-bottom: 16px;
            opacity: 0.5;
        }
    </style>
</head>
<body>
    <header>
        <div class="container">
            <div class="header-content">
                <div class="logo">
                    <i class="fab fa-github"></i>
                    <span>GitHub Analytics</span>
                </div>
                <div class="user-info">
                    <i class="fas fa-user-circle"></i>
                    <span>Dashboard</span>
                </div>
            </div>
        </div>
    </header>

    <main class="container">
        <div class="dashboard">
            <div class="main-content">
                <!-- Token Section -->
                <div class="card">
                    <div class="card-header">
                        <i class="fas fa-key"></i>
                        <h2 class="card-title">GitHub Token</h2>
                    </div>
                    <p style="margin-bottom: 16px; color: var(--text-light);">
                        Для работы приложения требуется Personal Access Token. 
                        <a href="https://github.com/settings/tokens" target="_blank" style="color: var(--secondary);">Создать токен</a>
                    </p>
                    <form action="/token" method="post" id="tokenForm">
                        <div class="form-group">
                            <label class="form-label">GitHub Token</label>
                            <input type="password" name="token" class="form-input" placeholder="ghp_ваш_токен" required>
                        </div>
                        <button type="submit" class="btn btn-primary btn-block" id="tokenBtn">
                            <i class="fas fa-save"></i> Сохранить токен
                        </button>
                    </form>
                </div>

                <!-- Add Repository -->
                <div class="card">
                    <div class="card-header">
                        <i class="fas fa-plus-circle"></i>
                        <h2 class="card-title">Добавить репозиторий</h2>
                    </div>
                    <form action="/track" method="post" id="trackForm">
                        <div class="form-row">
                            <div class="form-group">
                                <label class="form-label">Владелец</label>
                                <input type="text" name="owner" class="form-input" placeholder="например, microsoft" required>
                            </div>
                            <div class="form-group">
                                <label class="form-label">Репозиторий</label>
                                <input type="text" name="repo" class="form-input" placeholder="например, vscode" required>
                            </div>
                        </div>
                        <button type="submit" class="btn btn-primary btn-block" id="trackBtn">
                            <i class="fas fa-plus"></i> Добавить для отслеживания
                        </button>
                    </form>
                </div>

                <!-- Tracked Repositories Widgets -->
                <div class="card">
                    <div class="card-header">
                        <i class="fas fa-chart-line"></i>
                        <h2 class="card-title">Мои репозитории</h2>
                    </div>
                    <div id="repoWidgets" class="repo-widgets">
                        <div class="empty-state">
                            <i class="fas fa-chart-bar"></i>
                            <h3>Нет отслеживаемых репозиториев</h3>
                            <p>Добавьте репозитории выше, чтобы видеть их статистику здесь</p>
                        </div>
                    </div>
                </div>

                <!-- Quick Stats -->
                <div class="card">
                    <div class="card-header">
                        <i class="fas fa-bolt"></i>
                        <h2 class="card-title">Быстрый сбор статистики</h2>
                    </div>
                    <form id="statsForm">
                        <div class="form-row">
                            <div class="form-group">
                                <label class="form-label">Владелец</label>
                                <input type="text" id="quickOwner" class="form-input" placeholder="владелец репозитория" required>
                            </div>
                            <div class="form-group">
                                <label class="form-label">Репозиторий</label>
                                <input type="text" id="quickRepo" class="form-input" placeholder="название репозитория" required>
                            </div>
                        </div>
                        <button type="submit" class="btn btn-secondary btn-block" id="statsBtn">
                            <i class="fas fa-chart-bar"></i> Собрать статистику
                        </button>
                    </form>
                </div>

                <!-- Results -->
                <div id="result"></div>
            </div>

            <div class="sidebar">
                <!-- Auto Collect -->
                <div class="card auto-collect">
                    <div class="card-header">
                        <i class="fas fa-robot"></i>
                        <h2 class="card-title">Авто-сбор данных</h2>
                    </div>
                    <p style="margin-bottom: 16px; opacity: 0.9;">
                        Соберите статистику по всем отслеживаемым репозиториям одним кликом
                    </p>
                    <button onclick="runAutoCollect()" class="btn btn-block" id="autoCollectBtn">
                        <i class="fas fa-play"></i> Запустить авто-сбор
                    </button>
                </div>

                <!-- Info -->
                <div class="card">
                    <div class="card-header">
                        <i class="fas fa-info-circle"></i>
                        <h2 class="card-title">Информация</h2>
                    </div>
                    <div style="font-size: 0.875rem; color: var(--text-light);">
                        <p>📊 Собираемая статистика:</p>
                        <ul style="margin: 8px 0 8px 16px;">
                            <li>Звезды ⭐</li>
                            <li>Просмотры 👀</li>
                            <li>Клоны 💾</li>
                            <li>Форки 🍴</li>
                        </ul>
                        <p>Данные сохраняются навсегда</p>
                    </div>
                </div>
            </div>
        </div>
    </main>

    <footer>
        <div class="container">
            <p>GitHub Analytics Dashboard &copy; 2023 | Отслеживайте статистику ваших репозиториев</p>
        </div>
    </footer>

    <script>
        // Загрузить виджеты репозиториев
        async function loadRepoWidgets() {
            const repoWidgets = document.getElementById('repoWidgets');
            
            try {
                const response = await fetch('/tracked');
                const data = await response.json();
                
                if (data.repos && data.repos.length > 0) {
                    repoWidgets.innerHTML = data.repos.map(repo => `
                        <div class="repo-widget loading" id="widget-${repo.owner}-${repo.name}">
                            <div class="repo-widget-header">
                                <div class="repo-widget-info">
                                    <div class="repo-widget-name">${repo.name}</div>
                                    <div class="repo-widget-owner">${repo.owner}</div>
                                </div>
                                <div class="repo-widget-actions">
                                    <button class="refresh-btn" onclick="refreshRepo('${repo.owner}', '${repo.name}')" title="Обновить">
                                        <i class="fas fa-sync-alt"></i>
                                    </button>
                                </div>
                            </div>
                            <div class="repo-widget-stats">
                                <div class="repo-stat">
                                    <div class="repo-stat-value">-</div>
                                    <div class="repo-stat-label"><i class="fas fa-star"></i> Stars</div>
                                </div>
                                <div class="repo-stat">
                                    <div class="repo-stat-value">-</div>
                                    <div class="repo-stat-label"><i class="fas fa-eye"></i> Views</div>
                                </div>
                                <div class="repo-stat">
                                    <div class="repo-stat-value">-</div>
                                    <div class="repo-stat-label"><i class="fas fa-download"></i> Clones</div>
                                </div>
                            </div>
                            <div class="repo-widget-updated">
                                <i class="fas fa-clock"></i> Загрузка...
                            </div>
                        </div>
                    `).join('');

                    // Загружаем статистику для каждого репозитория
                    data.repos.forEach(repo => {
                        loadRepoStats(repo.owner, repo.name);
                    });
                } else {
                    repoWidgets.innerHTML = `
                        <div class="empty-state">
                            <i class="fas fa-chart-bar"></i>
                            <h3>Нет отслеживаемых репозиториев</h3>
                            <p>Добавьте репозитории выше, чтобы видеть их статистику здесь</p>
                        </div>
                    `;
                }
            } catch (error) {
                repoWidgets.innerHTML = '<div class="message message-error">Ошибка загрузки репозиториев</div>';
            }
        }

        // Загрузить статистику для конкретного репозитория
        async function loadRepoStats(owner, repo) {
            const widget = document.getElementById(`widget-${owner}-${repo}`);
            if (!widget) return;

            try {
                const response = await fetch(`/stats/${owner}/${repo}`, {
                    method: 'POST',
                    credentials: 'include'
                });
                
                if (response.ok) {
                    const data = await response.json();
                    
                    widget.classList.remove('loading');
                    widget.innerHTML = `
                        <div class="repo-widget-header">
                            <div class="repo-widget-info">
                                <div class="repo-widget-name">${repo}</div>
                                <div class="repo-widget-owner">${owner}</div>
                            </div>
                            <div class="repo-widget-actions">
                                <button class="refresh-btn" onclick="refreshRepo('${owner}', '${repo}')" title="Обновить">
                                    <i class="fas fa-sync-alt"></i>
                                </button>
                            </div>
                        </div>
                        <div class="repo-widget-stats">
                            <div class="repo-stat">
                                <div class="repo-stat-value">${data.data.stars}</div>
                                <div class="repo-stat-label"><i class="fas fa-star"></i> Stars</div>
                            </div>
                            <div class="repo-stat">
                                <div class="repo-stat-value">${data.data.views}</div>
                                <div class="repo-stat-label"><i class="fas fa-eye"></i> Views</div>
                            </div>
                            <div class="repo-stat">
                                <div class="repo-stat-value">${data.data.clones}</div>
                                <div class="repo-stat-label"><i class="fas fa-download"></i> Clones</div>
                            </div>
                            <div class="repo-stat">
                                <div class="repo-stat-value">${data.data.unique_visitors}</div>
                                <div class="repo-stat-label"><i class="fas fa-users"></i> Unique</div>
                            </div>
                            <div class="repo-stat">
                                <div class="repo-stat-value">${data.data.unique_clones}</div>
                                <div class="repo-stat-label"><i class="fas fa-user-check"></i> Unique Clones</div>
                            </div>
                            <div class="repo-stat">
                                <div class="repo-stat-value">${data.data.forks}</div>
                                <div class="repo-stat-label"><i class="fas fa-code-branch"></i> Forks</div>
                            </div>
                        </div>
                        <div class="repo-widget-updated">
                            <i class="fas fa-clock"></i> Обновлено: ${new Date().toLocaleTimeString()}
                        </div>
                    `;
                } else {
                    widget.classList.remove('loading');
                    widget.innerHTML = `
                        <div class="repo-widget-header">
                            <div class="repo-widget-info">
                                <div class="repo-widget-name">${repo}</div>
                                <div class="repo-widget-owner">${owner}</div>
                            </div>
                        </div>
                        <div style="text-align: center; color: var(--danger); padding: 20px;">
                            <i class="fas fa-exclamation-triangle"></i>
                            <div>Ошибка загрузки</div>
                        </div>
                    `;
                }
            } catch (error) {
                widget.classList.remove('loading');
                widget.innerHTML = `
                    <div class="repo-widget-header">
                        <div class="repo-widget-info">
                            <div class="repo-widget-name">${repo}</div>
                            <div class="repo-widget-owner">${owner}</div>
                        </div>
                    </div>
                    <div style="text-align: center; color: var(--danger); padding: 20px;">
                        <i class="fas fa-exclamation-triangle"></i>
                        <div>Ошибка соединения</div>
                    </div>
                `;
            }
        }

        // Обновить статистику репозитория
        async function refreshRepo(owner, repo) {
            const widget = document.getElementById(`widget-${owner}-${repo}`);
            if (widget) {
                widget.classList.add('loading');
                await loadRepoStats(owner, repo);
            }
        }

        // Сбор статистики
        document.getElementById('statsForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const owner = document.getElementById('quickOwner').value;
            const repo = document.getElementById('quickRepo').value;
            const statsBtn = document.getElementById('statsBtn');
            const originalText = statsBtn.innerHTML;
            
            // Показать загрузку
            statsBtn.innerHTML = '<div class="loading"></div> Загрузка...';
            statsBtn.disabled = true;
            
            try {
                const response = await fetch(`/stats/${owner}/${repo}`, {
                    method: 'POST',
                    credentials: 'include'
                });
                
                const data = await response.json();
                
                if (response.ok) {
                    document.getElementById('result').innerHTML = `
                        <div class="card">
                            <div class="card-header">
                                <i class="fas fa-check-circle" style="color: var(--success);"></i>
                                <h2 class="card-title">Статистика для ${owner}/${repo}</h2>
                            </div>
                            <div class="stats-grid">
                                <div class="stat-card">
                                    <div class="stat-label"><i class="fas fa-star"></i> Звезды</div>
                                    <div class="stat-value">${data.data.stars}</div>
                                </div>
                                <div class="stat-card">
                                    <div class="stat-label"><i class="fas fa-eye"></i> Просмотры</div>
                                    <div class="stat-value">${data.data.views}</div>
                                </div>
                                <div class="stat-card">
                                    <div class="stat-label"><i class="fas fa-download"></i> Клоны</div>
                                    <div class="stat-value">${data.data.clones}</div>
                                </div>
                                <div class="stat-card">
                                    <div class="stat-label"><i class="fas fa-code-branch"></i> Форки</div>
                                    <div class="stat-value">${data.data.forks}</div>
                                </div>
                                <div class="stat-card">
                                    <div class="stat-label"><i class="fas fa-users"></i> Уникальные посетители</div>
                                    <div class="stat-value">${data.data.unique_visitors}</div>
                                </div>
                                <div class="stat-card">
                                    <div class="stat-label"><i class="fas fa-user-check"></i> Уникальные клоны</div>
                                    <div class="stat-value">${data.data.unique_clones}</div>
                                </div>
                            </div>
                            <div style="margin-top: 16px; font-size: 0.875rem; color: var(--text-light);">
                                <i class="fas fa-clock"></i> Данные собраны: ${new Date(data.data.collected_at).toLocaleString()}
                            </div>
                        </div>
                    `;
                    loadRepoWidgets(); // Обновить виджеты
                } else {
                    document.getElementById('result').innerHTML = `
                        <div class="message message-error">
                            <i class="fas fa-exclamation-triangle"></i>
                            <div>${data.detail || 'Произошла ошибка'}</div>
                        </div>
                    `;
                }
            } catch (error) {
                document.getElementById('result').innerHTML = `
                    <div class="message message-error">
                        <i class="fas fa-exclamation-triangle"></i>
                        <div>Ошибка соединения: ${error.message}</div>
                    </div>
                `;
            } finally {
                // Восстановить кнопку
                statsBtn.innerHTML = originalText;
                statsBtn.disabled = false;
            }
        });

        // Авто-сбор
        async function runAutoCollect() {
            const autoCollectBtn = document.getElementById('autoCollectBtn');
            const originalText = autoCollectBtn.innerHTML;
            
            autoCollectBtn.innerHTML = '<div class="loading"></div> Сбор данных...';
            autoCollectBtn.disabled = true;
            
            try {
                const response = await fetch('/auto-collect', {
                    method: 'POST',
                    credentials: 'include'
                });
                const data = await response.json();
                
                alert(data.message);
                loadRepoWidgets(); // Обновить виджеты после сбора
            } catch (error) {
                alert('Ошибка при авто-сборе: ' + error.message);
            } finally {
                autoCollectBtn.innerHTML = originalText;
                autoCollectBtn.disabled = false;
            }
        }

        // Добавить обработчики для форм
        document.getElementById('tokenForm').addEventListener('submit', function() {
            const btn = document.getElementById('tokenBtn');
            btn.innerHTML = '<div class="loading"></div> Сохранение...';
        });

        document.getElementById('trackForm').addEventListener('submit', function() {
            const btn = document.getElementById('trackBtn');
            btn.innerHTML = '<div class="loading"></div> Добавление...';
            // После добавления репозитория обновляем виджеты
            setTimeout(loadRepoWidgets, 1000);
        });

        // Загрузить виджеты при загрузке страницы
        document.addEventListener('DOMContentLoaded', loadRepoWidgets);

        // Авто-обновление каждые 5 минут
        setInterval(loadRepoWidgets, 5 * 60 * 1000);
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