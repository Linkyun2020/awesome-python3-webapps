#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = 'Michael Liao'

'''
JSON API definition.
'''

import json, logging, inspect, functools

class APIError(Exception):
    '''
    the base APIError which contains error(required), data(optional) and message(optional).
    '''
    def __init__(self, error, data='', message=''):
        super(APIError, self).__init__(message)
        self.error = error
        self.data = data
        self.message = message

class APIValueError(APIError):
    '''
    Indicate the input value has error or invalid. The data specifies the error field of input form.
    '''
    def __init__(self, field, message=''):
        super(APIValueError, self).__init__('value:invalid', field, message)

class APIResourceNotFoundError(APIError):
    '''
    Indicate the resource was not found. The data specifies the resource name.
    '''
    def __init__(self, field, message=''):
        super(APIResourceNotFoundError, self).__init__('value:notfound', field, message)

class APIPermissionError(APIError):
    '''
    Indicate the api has no permission.
    '''
    def __init__(self, message=''):
        super(APIPermissionError, self).__init__('permission:forbidden', 'permission', message)


#用于选择当前页面 
def get_page_index(page_str): 
	p = 1 #初始化页数取整 
	try: 
		p = int(page_str) 
	except ValueError as e: 
		pass 
	if p < 1: 
		p = 1 
	return p

class Page(object):
    # 数据库博客总数，初始页，每页显示的博客总数
    def __init__(self, item_count, page_index=1, page_size=10):
        self.item_count = item_count
        self.page_size = page_size
        # 一共所需要页的总数
        self.page_count = item_count // page_size + (1 if item_count % page_size > 0 else 0)
        # 加入数据库没有博客或全部博客总页数不足一页
        if (item_count == 0) or (page_index > self.page_count):
            self.offset = 0
            self.limit = 0
            self.page_index = 1
        else:
            self.page_index = page_index #初始页
            self.offset = self.page_size * (page_index - 1) #当前页数，应从数据库的那个序列博客开始显示
            self.limit = self.page_size # 当前页数，应从数据库的那个序列博客结束像素
        self.has_next = self.page_index < self.page_count #是否下一页
        self.has_previous = self.page_index > 1 #是否上一页

    def __str__(self):
        return 'item_count: %s, page_count: %s, page_index: %s, page_size: %s, offset: %s, limit: %s' % (self.item_count, self.page_count, self.page_index, self.page_size, self.offset, self.limit)

    __repr__ = __str__