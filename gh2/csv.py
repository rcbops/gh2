from __future__ import absolute_import

import argparse
import csv
import os

import github3


def make_parser():
    args = argparse.ArgumentParser(
        description='Convert GitHub issues to a CSV file'
    )
    # args.add_argument(
    #     '--fields', help='Names of data fields to take from an Issue'
    # )
    # args.add_argument(
    #     '--headers', help='Names of the column headers'
    # )
    args.add_argument(
        '--issue-state', help='Whether issues are closed, open, or both',
        choices=['open', 'closed', 'all'], default='all',
    )
    args.add_argument(
        '--output-file', help='Name of file to write the results to',
        default='gh2csv.csv',
    )
    args.add_argument(
        '--date-format', help='Way to format the dates when present',
        default='%m/%d/%Y',
    )
    args.add_argument(
        '--include-pull-requests',
        help='Toggles the inclusion of PRs in output',
        type=bool, default=False,
    )
    args.add_argument(
        'repository', help='Repository to retrieve issues from',
    )
    return args


def issues_for(owner, name, state, token):
    gh = github3.GitHub(token=token)
    repository = gh.repository(owner, name)
    return repository.issues(state=state, direction='asc')


def issue_to_list(fields, issue):
    attributes = (
        getattr(issue, field, None) if field is not None else None
        for field in fields
    )
    return [
        attr.encode('utf-8') if hasattr(attr, 'encode') else attr
        for attr in attributes
    ]


def format_dates(attributes, fmt):
    return [
        attr.strftime(fmt) if hasattr(attr, 'strftime') else attr
        for attr in attributes
    ]


def is_pull_request(issue):
    pr = issue.as_dict().get('pull_request')
    return pr and isinstance(pr, dict)


def write_rows(filename, headers, fields, issues, date_format, include_prs):
    with open(filename, 'w') as fd:
        writer = csv.writer(fd)
        writer.writerow(headers)
        for issue in issues:
            if not include_prs and is_pull_request(issue):
                continue
            writer.writerow(
                format_dates(
                    issue_to_list(fields, issue),
                    date_format,
                )
            )


def main():
    parser = make_parser()
    token = os.environ.get('GITHUB_TOKEN')
    if token is None:
        parser.exit(status=1,
                    message='No GITHUB_TOKEN specified by the user\n')
    args = parser.parse_args()

    repo_owner, repo_name = args.repository.split('/', 1)
    headers = [
        'ID', 'Link', 'Name', 'Backlog', 'Approved', 'Doing',
        'Needs Review', 'Dev Done'
    ]
    fields = [
        'number', 'html_url', 'title', 'created_at', None, None, None,
        'closed_at'
    ]

    write_rows(
        filename=args.output_file,
        headers=headers,
        fields=fields,
        issues=issues_for(
            owner=repo_owner,
            name=repo_name,
            state=args.issue_state,
            token=token,
        ),
        date_format=args.date_format,
        include_prs=args.include_pull_requests,
    )
