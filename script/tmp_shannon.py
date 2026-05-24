import sys
sys.stdout.reconfigure(encoding='utf-8')

from scrapling import Fetcher

print('='*80)
print('Shannon GitHub 搜索')
print('='*80)

fetcher = Fetcher()

# GitHub 搜索 Shannon 相关项目
print('\n【GitHub Topics: shannon】')
try:
    page = fetcher.get('https://github.com/topics/shannon', timeout=30)
    print(f'Status: {page.status}')

    # 查找仓库
    repos = page.find_all('article')
    if repos:
        print(f'Found {len(repos)} repositories:')
        for i, repo in enumerate(repos[:10]):
            name = repo.find('h3')
            desc = repo.find('p')
            link = repo.find('a')

            if name:
                print(f'\n[{i+1}] {name.text.strip()}')
            if desc:
                print(f'    Description: {desc.text.strip()[:100]}')
            if link:
                href = link.attrib.get('href', '')
                print(f'    URL: https://github.com{href}')
    else:
        print('No repositories found')

except Exception as e:
    print(f'Error: {e}')

# 搜索 Shannon 安全工具
print('\n\n【GitHub 搜索 Shannon 安全工具】')
search_queries = [
    'shannon+security',
    'shannon+exploit',
    'shannon+tool',
    'shannon+cipher',
]

for query in search_queries:
    try:
        page = fetcher.get(f'https://github.com/search?q={query}&type=repositories', timeout=15)
        links = page.find_all('a')
        relevant = [a for a in links if 'shannon' in (a.text + a.attrib.get('href', '')).lower()][:3]
        if relevant:
            print(f'\n{query}:')
            for link in relevant:
                href = link.attrib.get('href', '')
                text = link.text.strip()[:50]
                print(f'  {text} -> {href}')
    except:
        pass

# 检查 Shannon 相关的知名项目
print('\n\n【检查 Shannon 相关知名项目】')
projects = [
    'https://github.com/shannonio/shannon',
    'https://github.com/shannon',
    'https://github.com/Shannon-ai',
]

for url in projects:
    try:
        page = fetcher.get(url, timeout=15)
        if page.status == 200:
            title = page.find('title')
            print(f'\n{url}')
            print(f'  Title: {title.text.strip()[:80] if title else "N/A"}')

            desc = page.find('p')
            if desc:
                print(f'  Description: {desc.text.strip()[:100]}')
    except:
        pass
