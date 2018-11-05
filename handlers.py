import asyncio 
from coroweb import get,post
import re, time, json, logging, hashlib, base64, asyncio
from models import User, Comment, Blog, next_id
from aiohttp import web
from apis import APIValueError, APIResourceNotFoundError,APIError,get_page_index,Page
from config import configs
import markdown2


COOKIE_NAME = 'awesession' #用来在set_cookie中命名
_COOKIE_KEY = configs.session.secret #导入默认设置

# set_cookie的一个参数，生成cookie值
def user2cookie(user, max_age):
    '''
    Generate cookie str by user.
    '''
    # build cookie string by: id-expires-sha1，即id-到期时间-摘要算法
    expires = str(int(time.time() + max_age))
    s = '%s-%s-%s-%s' % (user.id, user.passwd, expires, _COOKIE_KEY)
    L = [user.id, expires, hashlib.sha1(s.encode('utf-8')).hexdigest()]
    return '-'.join(L)

# 解释cookie
async def cookie2user(cookie_str):
    '''
    Parse cookie and load user if cookie is valid.
    '''
    if not cookie_str:
        return None
    try:
        L = cookie_str.split('-') # 拆分字符串
        if len(L) != 3:
            return None
        uid, expires, sha1 = L
        if int(expires) < time.time(): #查看是否过期
            return None
        user = await User.find(uid)
        if user is None:
            return None
		# 用数据库生成字符串c并与cookie进行比较
        s = '%s-%s-%s-%s' % (uid, user.passwd, expires, _COOKIE_KEY)
        if sha1 != hashlib.sha1(s.encode('utf-8')).hexdigest():
            logging.info('invalid sha1')
            return None
        user.passwd = '******'
        return user
    except Exception as e:
        logging.exception(e)
        return None



#编写用于测试的URL处理函数 
@get('/')
async def index(request):
	summary = 'hello world.'
	blogs = [
		Blog(id='1', name='Test Blog', summary=summary, created_at=time.time()-120),
		Blog(id='2', name='Something New', summary=summary, created_at=time.time()-3600),
		Blog(id='3', name='Learn Swift', summary=summary, created_at=time.time()-7200)
	]
	return {
		'__template__': 'blogs.html',
		'blogs': blogs,
		'__user__': request.__user__
	}

# 显示注册页面
@get('/register')
async def register():
	return {
		'__template__': 'register.html'
	}

# email与password的通配符	
_RE_EMAIL = re.compile(r'^[a-z0-9\.\-\_]+\@[a-z0-9\-\_]+(\.[a-z0-9\-\_]+){1,4}$')
_RE_SHA1 = re.compile(r'^[0-9a-f]{40}$')

# 用户注册api，用来post信息的
@post('/api/users')
async def api_register_user(*, name, email, passwd):
    # 判断值是否正确
    if not name or not name.strip():
        raise APIValueError('name')
    if not email or not _RE_EMAIL.match(email):
        raise APIValueError('email')
    if not passwd or not _RE_SHA1.match(passwd):
        raise APIValueError('passwd')
    users = await User.findAll(where='email=?', args=[email])
    if len(users) > 0:
        raise APIError('register:failed', 'email', 'Email is already in use.')
    # 注册到数据库上
    uid = next_id()
    sha1_passwd = '%s:%s' % (uid, passwd)
    user = User(id=uid, name=name.strip(), email=email, passwd=hashlib.sha1(sha1_passwd.encode('utf-8')).hexdigest(), image='http://www.gravatar.com/avatar/%s?d=mm&s=120' % hashlib.md5(email.encode('utf-8')).hexdigest())
    await user.save()
    # make session cookie，并返回浏览器客户端
    r = web.Response()
    r.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=86400, httponly=True)
    user.passwd = '******'
    r.content_type = 'application/json'
    r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')
    return r

@get('/signin')
async def signin():
    return {
        '__template__': 'signin.html'
}

@get('/signout')
async def signout(request):
    referer = request.headers.get('Referer')
    r = web.HTTPFound(referer or '/')
    r.set_cookie(COOKIE_NAME, '-deleted-', max_age=0, httponly=True)
    logging.info('user signed out.')
    return r	
	
@post('/api/authenticate')
async def authenticate(*, email, passwd):
    if not email:
        raise APIValueError('email', 'Invalid email.')
    if not passwd:
        raise APIValueError('passwd', 'Invalid password.')
    users = await User.findAll('email=?', [email])
    logging.info(users)
    if len(users) == 0:
        raise APIValueError('email', 'Email not exist.')
    user = users[0]
    # check passwd:
    sha1 = hashlib.sha1()
    sha1.update(user.id.encode('utf-8'))
    sha1.update(b':')
    sha1.update(passwd.encode('utf-8'))
    if user.passwd != sha1.hexdigest():
        raise APIValueError('passwd', 'Invalid password.')
    # authenticate ok, set cookie:
    r = web.Response()
    r.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=86400, httponly=True)
    user.passwd = '******'
    r.content_type = 'application/json'
    r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')
    return r


def check_admin(request):
    if request.__user__ is None or not request.__user__.admin:
        raise APIPermissionError()
	
@post('/api/blogs')
async def api_create_blog(request, *, name, summary, content):
    check_admin(request)
    if not name or not name.strip():
        raise APIValueError('name', 'name cannot be empty.')
    if not summary or not summary.strip():
        raise APIValueError('summary', 'summary cannot be empty.')
    if not content or not content.strip():
        raise APIValueError('content', 'content cannot be empty.')
    blog = Blog(user_id=request.__user__.id, user_name=request.__user__.name, user_image=request.__user__.image, name=name.strip(), summary=summary.strip(), content=content.strip())
    await blog.save()
    return blog

@get('/manage/blogs/create')
async def manage_create_blog(request):
    return {
        '__template__': 'manage_blog_edit.html',
        'id': '',
        'action': '/api/blogs',
        '__user__': request.__user__	
}

@get('/api/blogs')
async def api_blogs(*, page='1'):
    page_index = get_page_index(page)
    num = await Blog.findNumber('count(id)') #查询日志总数
    p = Page(num, page_index)
    if num == 0: #数据库没日志
        return dict(page=p, blogs=())
    blogs = await Blog.findAll(orderBy='created_at desc', limit=(p.offset, p.limit)) #选取对应的日志
    return dict(page=p, blogs=blogs) #返回管理页面信息，及显示日志数

@get('/manage/blogs')
async def manage_blogs(*, page='1'):
    return {
        '__template__': 'manage_blogs.html',
        'page_index': get_page_index(page)
    }

@get('/api/blogs/{id}')
async def api_get_blog(*, id):
    blog = await Blog.find(id)
    return blog

def text2html(text):
    lines = map(lambda s: '<p>%s</p>' % s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'), filter(lambda s: s.strip() != '', text.split('\n')))
    return ''.join(lines)

@get('/blog/{id}')
async def get_blog(id):
    blog = await Blog.find(id)
    comments = await Comment.findAll('blog_id=?', [id], orderBy='created_at desc')
    for c in comments:
        c.html_content = text2html(c.content)
    blog.html_content = markdown2.markdown(blog.content)
    return {
        '__template__': 'blog.html',
        'blog': blog,
        'comments': comments
}