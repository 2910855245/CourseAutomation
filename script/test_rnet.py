import sys
sys.path.insert(0, '/www/wwwroot/anti_course')
from infrastructure.chaoxing_session import ChaoxingSession

session = ChaoxingSession()
print(f'impersonate: {session._impersonate}')
print(f'UA: {session.UA[:50]}...')

ok = session.login('19136434661', 'woainima123')
print(f'login: {ok}, uid: {session.uid}')

if ok:
    # Test get
    resp = session.get('https://sso.chaoxing.com/apis/login/userLogin4Uname.do')
    print(f'get status: {resp.status_code}')
    print(f'get text type: {type(resp.text())}')
    print(f'get text[:100]: {resp.text()[:100]}')

    # Test get_json
    data = session.get_json('https://sso.chaoxing.com/apis/login/userLogin4Uname.do')
    print(f'get_json: name={data.get("msg", {}).get("name", "?")}')

    # Test post
    resp2 = session.post('https://mooc1-1.chaoxing.com/mooc-ans/visit/courselistdata',
        data={'courseType': '1', 'courseFolderId': '0', 'baseEducation': '0', 'superstarClass': '', 'courseFolderSize': '0'},
        referer='https://mooc1.chaoxing.com/')
    print(f'post status: {resp2.status_code}')
    html = resp2.text()
    print(f'post text length: {len(html)}')
    print(f'post text[:200]: {html[:200]}')
