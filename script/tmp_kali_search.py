import sys
sys.stdout.reconfigure(encoding='utf-8')

from scrapling import Fetcher

print('='*80)
print('Kali Linux AI 渗透测试工具搜索')
print('='*80)

fetcher = Fetcher()

# 搜索 Kali + AI 渗透测试项目
print('\n【GitHub 搜索 Kali AI 渗透测试】')
search_queries = [
    'kali+ai+pentesting',
    'kali+ai+security',
    'kali+linux+ai+tool',
    'bootable+kali+ai',
]

for query in search_queries:
    try:
        print(f'\n搜索: {query}')
        page = fetcher.get(f'https://github.com/search?q={query}&type=repositories', timeout=15)

        links = page.find_all('a')
        relevant = [a for a in links if 'kali' in (a.text + a.attrib.get('href', '')).lower()][:3]

        if relevant:
            for link in relevant:
                href = link.attrib.get('href', '')
                text = link.text.strip()[:50]
                if text and href:
                    print(f'  {text} -> {href}')
    except Exception as e:
        print(f'  Error: {e}')

# 检查 Topics 页面
print('\n\n【GitHub Topics: kali-ai】')
topics = [
    'kali-linux',
    'kali',
    'pentesting-ai',
    'ai-security',
]

for topic in topics:
    try:
        page = fetcher.get(f'https://github.com/topics/{topic}', timeout=15)
        if page.status == 200:
            repos = page.find_all('article')
            if repos:
                print(f'\n{topic} ({len(repos)} repos):')
                for repo in repos[:3]:
                    name = repo.find('h3')
                    desc = repo.find('p')
                    if name:
                        print(f'  - {name.text.strip()}')
                    if desc:
                        print(f'    {desc.text.strip()[:80]}')
    except:
        pass

print('\n' + '='*80)
print('【结论】')
print('='*80)
print('''
如果你要使用 AI 渗透测试工具，通常需要:

1. 【Kali Linux】(推荐)
   - 预装了 600+ 安全工具
   - 专门用于渗透测试
   - 支持 Live USB 运行

2. 【其他选择】
   - Parrot OS - 轻量级安全系统
   - BlackArch - Arch Linux 安全版
   - 在现有系统上手动安装工具

3. 【Windows 上使用】
   - WSL2 + Kali
   - 虚拟机 (VMware/VirtualBox)
   - Docker 容器

4. 【不需要 Kali 的情况】
   - 单一工具 (如 nmap, metasploit)
   - Python 安全库
   - 在线工具
''')
