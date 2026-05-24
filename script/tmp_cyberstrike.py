import sys
sys.stdout.reconfigure(encoding='utf-8')

from scrapling import Fetcher

print('='*80)
print('CyberStrike 搜索')
print('='*80)

fetcher = Fetcher()

# GitHub 搜索
print('\n【GitHub 搜索 CyberStrike】')
try:
    page = fetcher.get('https://github.com/search?q=cyberstrike&type=repositories', timeout=30)
    print(f'Status: {page.status}')

    links = page.find_all('a')
    cyberstrike_links = [a for a in links if 'cyberstrike' in (a.text + a.attrib.get('href', '')).lower()]
    print(f'Found {len(cyberstrike_links)} links:')
    for link in cyberstrike_links[:15]:
        href = link.attrib.get('href', '')
        text = link.text.strip()[:60]
        if text and href:
            print(f'  {text} -> {href}')
except Exception as e:
    print(f'Error: {e}')

# CSDN 搜索
print('\n【CSDN 搜索 CyberStrike】')
try:
    page = fetcher.get('https://so.csdn.net/so/search?q=cyberstrike&t=all', timeout=30)
    print(f'Status: {page.status}')

    links = page.find_all('a')
    csdn_links = [a for a in links if len(a.text.strip()) > 5]
    print(f'Found {len(csdn_links)} links:')
    for link in csdn_links[:15]:
        href = link.attrib.get('href', '')
        text = link.text.strip()[:60]
        if text and href and 'cyberstrike' in text.lower():
            print(f'  {text} -> {href}')
except Exception as e:
    print(f'Error: {e}')

# 直接搜索相关项目
print('\n【搜索相关安全工具项目】')
try:
    # 搜索一些知名的安全工具仓库
    repos = [
        'github.com/CyberStrike-Team',
        'github.com/topics/cyberstrike',
        'github.com/search?q=cyber+strike',
    ]

    for repo_url in repos:
        try:
            page = fetcher.get(f'https://{repo_url}', timeout=15)
            links = page.find_all('a')
            relevant = [a for a in links if len(a.text.strip()) > 3][:5]
            if relevant:
                print(f'\n{repo_url}:')
                for link in relevant:
                    href = link.attrib.get('href', '')
                    text = link.text.strip()[:50]
                    print(f'  {text} -> {href}')
        except:
            pass
except Exception as e:
    print(f'Error: {e}')
