import sys
sys.stdout.reconfigure(encoding='utf-8')

from scrapling import Fetcher

print('='*80)
print('CyberStrike 详细搜索')
print('='*80)

fetcher = Fetcher()

# 直接访问可能的 CyberStrike 项目页面
urls = [
    'https://github.com/CyberStrike-Team/CyberStrike',
    'https://github.com/OWASP/CyberStrike',
    'https://github.com/topics/cyberstrike',
    'https://github.com/search?q=cyberstrike+security&type=repositories',
]

print('\n【检查可能的 CyberStrike 项目】')
for url in urls:
    try:
        print(f'\nChecking: {url}')
        page = fetcher.get(url, timeout=15)
        print(f'Status: {page.status}')

        # 获取页面标题
        title = page.find('title')
        if title:
            print(f'Title: {title.text.strip()[:80]}')

        # 查找项目描述
        desc = page.find('p', class_='f4')
        if desc:
            print(f'Description: {desc.text.strip()[:100]}')

        # 查找 README 内容
        readme = page.find('article', class_='markdown-body')
        if readme:
            print(f'README preview: {readme.text.strip()[:200]}')

    except Exception as e:
        print(f'Error: {e}')

# 搜索其他安全工具
print('\n\n【搜索相关安全工具】')
security_tools = [
    'https://github.com/The-Art-of-Hacking/h4cker',
    'https://github.com/swisskyrepo/PayloadsAllTheThings',
    'https://github.com/hacktoolspack/hacktools',
]

for url in security_tools:
    try:
        page = fetcher.get(url, timeout=15)
        title = page.find('title')
        if title:
            print(f'{url.split("/")[-1]}: {title.text.strip()[:60]}')
    except:
        pass

print('\n' + '='*80)
print('注意: GitHub 搜索需要登录才能看到完整结果')
print('建议直接访问: https://github.com/search?q=cyberstrike')
print('='*80)
