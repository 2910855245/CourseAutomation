import sys
sys.stdout.reconfigure(encoding='utf-8')

from scrapling import Fetcher

print('='*80)
print('CyberStrike GitHub 详情')
print('='*80)

fetcher = Fetcher()

# 检查找到的 CyberStrike 用户/组织
users = [
    ('https://github.com/cyberstrike', 'CyberStrike (Chris Scott)'),
    ('https://github.com/cyber-strike', 'Cyber Strike'),
]

for url, name in users:
    print(f'\n【{name}】')
    print(f'URL: {url}')

    try:
        page = fetcher.get(url, timeout=30)
        print(f'Status: {page.status}')

        # 获取用户信息
        bio = page.find('div', class_='user-profile-bio')
        if bio:
            print(f'Bio: {bio.text.strip()[:200]}')

        # 获取仓库列表
        repos = page.find_all('div', itemprop='owns')
        if repos:
            print(f'\nRepositories ({len(repos)}):')
            for i, repo in enumerate(repos[:10]):
                name_elem = repo.find('a', itemprop='name codeRepository')
                if name_elem:
                    repo_name = name_elem.text.strip()
                    repo_url = name_elem.attrib.get('href', '')
                    print(f'  [{i+1}] {repo_name} -> https://github.com{repo_url}')

                desc = repo.find('p', itemprop='description')
                if desc:
                    print(f'      Description: {desc.text.strip()[:100]}')
        else:
            print('No public repositories found')

            # 尝试其他选择器
            links = page.find_all('a')
            repo_links = [a for a in links if a.attrib.get('itemprop', '') == 'name codeRepository']
            if repo_links:
                print(f'\nFound {len(repo_links)} repositories:')
                for link in repo_links[:10]:
                    href = link.attrib.get('href', '')
                    text = link.text.strip()
                    print(f'  - {text} -> https://github.com{href}')

    except Exception as e:
        print(f'Error: {e}')

print('\n' + '='*80)
print('总结')
print('='*80)
print('''
找到的 CyberStrike 相关 GitHub 账号:
1. CyberStrike (Chris Scott) - https://github.com/cyberstrike
2. Cyber Strike - https://github.com/cyber-strike

这些可能是个人开发者或安全研究人员的账号。
如果你在寻找特定的安全工具或项目，请提供更多信息。
''')
