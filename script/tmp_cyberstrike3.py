import sys
sys.stdout.reconfigure(encoding='utf-8')

from scrapling import Fetcher

print('='*80)
print('CyberStrike GitHub Topics 详情')
print('='*80)

fetcher = Fetcher()

# 访问 GitHub Topics 页面
print('\n【GitHub Topics: cyberstrike】')
try:
    page = fetcher.get('https://github.com/topics/cyberstrike', timeout=30)
    print(f'Status: {page.status}')

    # 查找仓库列表
    repos = page.find_all('article')
    if repos:
        print(f'Found {len(repos)} repositories:')
        for i, repo in enumerate(repos):
            # 获取仓库名称
            name = repo.find('h3')
            if name:
                name_text = name.text.strip()
            else:
                name_text = 'Unknown'

            # 获取描述
            desc = repo.find('p')
            desc_text = desc.text.strip()[:100] if desc else 'No description'

            # 获取链接
            link = repo.find('a')
            href = link.attrib.get('href', '') if link else ''

            print(f'\n[{i+1}] {name_text}')
            print(f'    Description: {desc_text}')
            print(f'    URL: https://github.com{href}')
    else:
        print('No repositories found in topics page')

        # 尝试其他选择器
        links = page.find_all('a')
        repo_links = [a for a in links if '/CyberStrike' in a.attrib.get('href', '')]
        print(f'Found {len(repo_links)} CyberStrike links:')
        for link in repo_links[:10]:
            href = link.attrib.get('href', '')
            text = link.text.strip()[:50]
            print(f'  {text} -> https://github.com{href}')

except Exception as e:
    print(f'Error: {e}')

# 尝试直接访问一些可能的 CyberStrike 组织/用户页面
print('\n\n【检查 CyberStrike 相关组织】')
orgs = [
    'https://github.com/cyberstrike',
    'https://github.com/CyberStrike',
    'https://github.com/cyber-strike',
]

for url in orgs:
    try:
        page = fetcher.get(url, timeout=15)
        if page.status == 200:
            title = page.find('title')
            print(f'\n{url}')
            print(f'  Title: {title.text.strip()[:80] if title else "N/A"}')

            # 查找仓库列表
            repos = page.find_all('a', itemprop='name codeRepository')
            if repos:
                print(f'  Repositories:')
                for repo in repos[:5]:
                    href = repo.attrib.get('href', '')
                    text = repo.text.strip()
                    print(f'    - {text} -> https://github.com{href}')
    except:
        pass
