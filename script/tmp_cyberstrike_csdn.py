import sys
sys.stdout.reconfigure(encoding='utf-8')

from scrapling import Fetcher

print('='*80)
print('CyberStrike CSDN 搜索')
print('='*80)

fetcher = Fetcher()

# CSDN 搜索
print('\n【CSDN 搜索 CyberStrike】')
try:
    page = fetcher.get('https://so.csdn.net/so/search?q=cyberstrike&t=all', timeout=30)
    print(f'Status: {page.status}')

    # 查找搜索结果
    results = page.find_all('div', class_='list-item')
    if results:
        print(f'Found {len(results)} results:')
        for i, result in enumerate(results[:10]):
            title = result.find('a')
            if title:
                href = title.attrib.get('href', '')
                text = title.text.strip()[:80]
                print(f'[{i+1}] {text}')
                print(f'    URL: {href}')
    else:
        print('No results found with list-item selector')

        # 尝试其他选择器
        articles = page.find_all('article')
        if articles:
            print(f'Found {len(articles)} articles:')
            for i, article in enumerate(articles[:10]):
                title = article.find('a')
                if title:
                    href = title.attrib.get('href', '')
                    text = title.text.strip()[:80]
                    print(f'[{i+1}] {text}')
                    print(f'    URL: {href}')

        # 查找所有链接
        links = page.find_all('a')
        csdn_links = [a for a in links if 'cyberstrike' in (a.text + a.attrib.get('href', '')).lower()]
        if csdn_links:
            print(f'\nFound {len(csdn_links)} CyberStrike links:')
            for link in csdn_links[:10]:
                href = link.attrib.get('href', '')
                text = link.text.strip()[:60]
                print(f'  {text} -> {href}')

except Exception as e:
    print(f'Error: {e}')

# 搜索相关内容
print('\n\n【搜索相关安全内容】')
search_terms = ['cyber strike', '网络安全攻击', '渗透测试工具']

for term in search_terms:
    try:
        page = fetcher.get(f'https://so.csdn.net/so/search?q={term}&t=all', timeout=15)
        links = page.find_all('a')
        articles = [a for a in links if len(a.text.strip()) > 10][:3]
        if articles:
            print(f'\n{term}:')
            for article in articles:
                href = article.attrib.get('href', '')
                text = article.text.strip()[:50]
                print(f'  - {text} -> {href}')
    except:
        pass
