import sys
sys.stdout.reconfigure(encoding='utf-8')

from scrapling import Fetcher

print('='*80)
print('Shannon 详细项目搜索')
print('='*80)

fetcher = Fetcher()

# 检查 Shannon 用户的仓库
print('\n【Shannon 用户仓库】')
users = [
    ('https://github.com/shannon', 'Shannon Poole'),
    ('https://github.com/Shannon-ai', 'SHANNON AI'),
]

for url, name in users:
    print(f'\n{name}: {url}')
    try:
        page = fetcher.get(url, timeout=20)
        print(f'Status: {page.status}')

        # 查找仓库
        repos = page.find_all('div', itemprop='owns')
        if repos:
            print(f'Repositories ({len(repos)}):')
            for i, repo in enumerate(repos[:5]):
                name_elem = repo.find('a', itemprop='name codeRepository')
                if name_elem:
                    repo_name = name_elem.text.strip()
                    repo_url = name_elem.attrib.get('href', '')
                    print(f'  [{i+1}] {repo_name} -> https://github.com{repo_url}')

                desc = repo.find('p', itemprop='description')
                if desc:
                    print(f'      {desc.text.strip()[:100]}')
        else:
            print('No public repositories')
    except Exception as e:
        print(f'Error: {e}')

# 搜索 Shannon 相关的安全工具
print('\n\n【Shannon 安全相关项目】')
security_projects = [
    'https://github.com/topics/shannon+security',
    'https://github.com/topics/shannon+exploit',
    'https://github.com/topics/shannon+cipher',
    'https://github.com/topics/shannon+entropy',
]

for url in security_projects:
    try:
        page = fetcher.get(url, timeout=15)
        if page.status == 200:
            repos = page.find_all('article')
            if repos:
                print(f'\n{url.split("/")[-1]}:')
                for repo in repos[:3]:
                    name = repo.find('h3')
                    desc = repo.find('p')
                    if name:
                        print(f'  - {name.text.strip()}')
                    if desc:
                        print(f'    {desc.text.strip()[:80]}')
    except:
        pass

# Shannon 相关的知名安全概念
print('\n\n【Shannon 安全概念】')
print('''
Shannon 在安全领域通常指:

1. Shannon 熵 (信息熵)
   - 用于密码学和信息论
   - 测量信息的不确定性
   - 应用于密码强度评估

2. Shannon 密码
   - 流密码的基础理论
   - Claude Shannon 提出的密码学原理

3. Shannon-Fano 编码
   - 数据压缩算法
   - 前缀编码的一种

4. Shannon 极限定理
   - 信道编码的基础
   - 通信安全的理论基础
''')
