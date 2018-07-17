#!/usr/bin/env python
# encoding: utf-8

import gitlab
from json import loads
import re
import requests
from sanic import Sanic
from sanic.response import json
from sanic.response import text
import time


app = Sanic()


class GitlabAccess(object):
    def __init__(self):
        # self.gl = gitlab.Gitlab(url='http://127.0.0.1/', private_token='xxxxxxxx', api_version='3')
        self.gl = gitlab.Gitlab(url='http://xxxx.com/', private_token='xxxxx', api_version='3')

    def get_project_obj(self, pro_id):
        return self.gl.projects.get(pro_id)


def check_readme_filesize(project, project_ref):
    """
    Check for readme file existence and file size
    :param project: string
    :param project_ref: string
    :return: list [0] -> status_code [1] -> status_msg
    """
    # print("running check_readme_filesize")
    bran_prt = re.compile(r'[D|d][O|o][C|c]/[R|r][E|e][A|a][D|d][M|m][E|e]$')
    file_part = re.compile(r'[R|r][E|e][A|a][D|d][M|m][E|e]\.[M|m][D|d]$')

    branch_name = bran_prt.findall(project_ref)[0]
    pro_path, pro_ref = branch_name.split('/')
    repo_trees = project.repository_tree(path=pro_path, ref_name=branch_name)

    if 1 != len(repo_trees) and repo_trees[0]["type"] != "blob":
        return 1, 'File check does not pass'
    if file_part.findall(repo_trees[0]['name']).__len__() == 0:
        return 1, 'Filename check failed'

    file_path = '{path}/{name}'.format(path=pro_path, name=repo_trees[0]['name'])
    size = project.files.get(file_path=file_path, ref=branch_name)
    if 0 == size:
        return 1, 'File is Empty'
    return 0, 'OK'


def branch_is_readme(branches_ref):
    """
    Check if the branch is a readme branch
    :param branches_ref: include readme branch, such as 'refs/heads/doc/readme'
    :return: list [0] -> status_code [1] -> status_msg
    """
    # print("running branch_is_readme")
    branches_prt = re.compile(r'[D|d][O|o][C|c]/[R|r][E|e][A|a][D|d][M|m][E|e]$')
    if branches_prt.findall(branches_ref).__len__() == 0:
        return 1, 'No readme update'
    else:
        return 0, 'OK'


def compare_branches(project, project_ref):
    """
    compare branches is change
    :param project: string
    :param project_ref: string
    :return: list [0] -> status_code [1] -> status_msg
    """
    bran_com = re.compile(r'[D|d][O|o][C|c]/[R|r][E|e][A|a][D|d][M|m][E|e]$')
    branch_name = bran_com.findall(project_ref)[0]
    result = project.repository_compare('master', branch_name)
    if result['diffs'].__len__() == 0:
        return 1, 'no change'
    if '.go' in result['diffs'][0]['new_path']:
        return 1, '{branch} branch contains ".go" source file changes'.format(branch=branch_name)
    return 0, 'OK'


def git_merge(project, ref):
    """
    Create merge requests and merge readme branch to master
    :param project: string
    :param ref: string
    :return: list [0] -> status_code [1] -> status_msg
    """

    # create merge requests
    mr_part = re.compile(r'[D|d][O|o][C|c]/[R|r][E|e][A|a][D|d][M|m][E|e]$')
    source_branch = mr_part.findall(ref)[0]
    try:
        mr_message = {
            # 'source_branch': 'doc/readme',
            'source_branch': source_branch,
            'target_branch': 'master',
            'title': 'merge readme'
        }
        mr = project.mergerequests.create(mr_message)
        mr_result = mr.merge()
        if mr_result is not None:
            return 1, str(mr_result)
        else:
            return 0, 'OK'
    except (gitlab.GitlabMRClosedError, gitlab.GitlabCreateError) as err:
        return 1, err.response_code


def get_project_info(body):
    """
    Check the HTTP body sent by the system hook
    :param body: dict
    :return: list [0] -> status_code [1] -> status_msg
    """
    print(body)
    project_info = dict()
    project_info['project_event_name'] = body.get('event_name')

    # checkout gitlab event
    if body['event_name'] != 'push':
        return 1, 'The event is not push'
    if 'ref' in body:
        project_info['ref'] = body.get('ref')
    else:
        return 1, 'No ref updates'
    project_info['user_name'] = body.get('user_name')
    project_info['user_email'] = body.get('user_email')
    project_info['project_id'] = body.get('project_id')

    # To check for non-project or non-branch operations, delete or add users, etc.
    if 'project' in body:
        project_info['project_name'] = body['project']['name']
        project_info['path_with_namespace'] = body['project']['path_with_namespace']
    else:
        return 1, 'No project updates'

    print(body['event_name'], body.get('ref'), body['project']['name'], body["user_name"], body["user_email"],)

    if 'repository' in body:
        project_info['msg_description'] = body['repository']['description']
    else:
        return 1, 'No repository updates'

    # Delete branches check
    if body['after'] == '0000000000000000000000000000000000000000' and body['checkout_sha'] == None:
        return 1, 'Delete project branches'

    return project_info


def notification(user_email, project, branches, message):
    """
    notification
    :param user_email: string
    :param project: string
    :param branches: string
    :param message: string
    :return: list [0] -> status_code [1] -> status_msg
    """
    # print("running notification")
    branches_prt = re.compile(r'[D|d][O|o][C|c]/[R|r][E|e][A|a][D|d][M|m][E|e]$')
    branches_s = branches_prt.findall(branches)[0]

    # notify message format
    content = '项目名称: {project}\n\n' \
              '分支名称: {branches}\n' \
              '具体消息: {message}\n\n' \
              '通知时间: {time}'.format(project=project, branches=branches_s, message=message,
                                    time=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))

    r = requests.post('http://login-in.codoon.com/api/send_weixin_msg',
                      data={'touseridlist': user_email,
                            'content': content})
    if r.status_code != 200:
        # print('notification failed')
        return 1, 'notify failed'
    else:
        return 0, 'notify success'


def test_case(request_case):
    """
    For test case
    :param request_case: http request,json
    :return: string
    """
    dict_body = loads(request_case.body)
    if 'name' in dict_body.keys() and dict_body['name'] == 'Ruby':
        return 'TEST'
    else:
        pass


@app.route('/readme', methods=['POST'])
async def http_server(request):
    """
    Listening to the local 8888 port and accepting messages from the git lab system
    :param request:
    :return:
    """

    if test_case(request) == 'TEST':
        return json(request.body)
    info = get_project_info(loads(request.body))
    if not isinstance(info, dict) and 1 == info[0]:
        return text(info[1])
    gitlab_obj = GitlabAccess()

    # test for online gitlab
    project = gitlab_obj.get_project_obj(int(info['project_id']))

    # 检测更新的分支是否是 doc/readme
    res = branch_is_readme(info['ref'])
    # print(res[0])
    if 0 != res[0]:
        return text(res[1])

    # 检测readme目录是否只有一个文件
    # res = check_readme_filesize(project, info['ref'])
    # # print(res[0], res[1])
    # if 0 != res[0]:
    #     return text(res[1])

    # compare branches
    res = compare_branches(project, info['ref'])
    # print(res[0], res[1])
    if 0 != res[0]:
        notification(info['user_email'], info['path_with_namespace'], info['ref'], res[1])
        return text(res[1])

    # merge readme分支
    res = git_merge(project, info['ref'])
    # print(res[0], res[1])
    if 0 != res[0]:
        if 405 == res[1]:
            notification(info['user_email'], info['path_with_namespace'], info['ref'], res[1])
        elif 409 == res[1]:
            notification(info['user_email'], info['path_with_namespace'],
                         info['ref'], '409:This merge request already exists')
        else:
            notification(info['user_email'], info['path_with_namespace'], info['ref'], 'merge failed')
        return text(res[1])

    # 企业微信消息通知
    res = notification(info['user_email'], info['path_with_namespace'], info['ref'], "Merged Successfully")
    # print(res[0])
    if 0 != res[0]:
        return text(res[1])

    return text('exit')


@app.route('/', methods=['POST'])
async def system_hooks(request):
    test_case(request)
    return json(request.body)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8888, access_log=True)
