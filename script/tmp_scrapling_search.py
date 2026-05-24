import sys
sys.stdout.reconfigure(encoding='utf-8')

from scrapling import Fetcher

print('='*80)
print('CrowdStrike 事件搜索')
print('='*80)

# 使用 scrapling Fetcher 搜索
fetcher = Fetcher()

# GitHub 搜索
print('\n【GitHub 搜索 CrowdStrike】')
try:
    page = fetcher.get('https://github.com/search?q=crowdstrike&type=repositories', timeout=30)
    print(f'Status: {page.status}')

    # 查找仓库列表
    repos = page.find_all('a', class_='v-align-middle')
    if repos:
        print(f'Found {len(repos)} repositories:')
        for i, repo in enumerate(repos[:10]):
            href = repo.attrib.get('href', '')
            text = repo.text.strip()
            print(f'  [{i+1}] {text} -> https://github.com{href}')
    else:
        print('No repositories found with that selector')

        # 尝试其他选择器
        links = page.find_all('a')
        crowdstrike_links = [a for a in links if 'crowdstrike' in (a.text + a.attrib.get('href', '')).lower()]
        print(f'Found {len(crowdstrike_links)} links with "crowdstrike":')
        for link in crowdstrike_links[:10]:
            href = link.attrib.get('href', '')
            text = link.text.strip()[:50]
            print(f'  {text} -> {href}')

except Exception as e:
    print(f'Error: {e}')

# CSDN 搜索
print('\n【CSDN 搜索 CrowdStrike】')
try:
    page = fetcher.get('https://so.csdn.net/so/search?q=crowdstrike&t=all', timeout=30)
    print(f'Status: {page.status}')

    # 查找文章列表
    articles = page.find_all('div', class_='list-item')
    if articles:
        print(f'Found {len(articles)} articles:')
        for i, article in enumerate(articles[:10]):
            title = article.find('a')
            if title:
                href = title.attrib.get('href', '')
                text = title.text.strip()[:50]
                print(f'  [{i+1}] {text} -> {href}')
    else:
        print('No articles found with that selector')

        # 尝试其他选择器
        links = page.find_all('a')
        csdn_links = [a for a in links if 'crowdstrike' in (a.text + a.attrib.get('href', '')).lower()]
        print(f'Found {len(csdn_links)} links with "crowdstrike":')
        for link in csdn_links[:10]:
            href = link.attrib.get('href', '')
            text = link.text.strip()[:50]
            print(f'  {text} -> {href}')

except Exception as e:
    print(f'Error: {e}')

print('\n' + '='*80)
print('CrowdStrike 事件简介')
print('='*80)
print('''
2024年7月19日，CrowdStrike Falcon传感器的一次错误更新导致全球大规模IT故障。

影响范围:
- 全球约850万台Windows电脑蓝屏
- 航空、银行、医疗、政府等多个行业受影响
- 被称为"历史上最大规模的IT故障"

原因:
- CrowdStrike Falcon传感器的配置更新文件(channel file)有bug
- 导致Windows内核崩溃(BSOD)
- 需要手动逐台修复

修复方法:
1. 进入安全模式
2. 删除 C:\Windows\System32\drivers\CrowdStrike\C-00000291*.sys 文件
3. 重启电脑
''')
