from __future__ import absolute_import

import argparse
import collections
import datetime
import csv
import itertools
import os

import cachecontrol
import cachecontrol.caches
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
        action='store_true', default=False,
    )
    args.add_argument(
        '--skip-date-normalization',
        help='By default, if a sequence of dates are not sequential, the tool '
             'will coerce them to look sequential.',
        action='store_true', default=False,
    )
    args.add_argument(
        '--include-labels',
        help='By default, the output will not include columns for the labels '
             'associated with the issue.',
        action='store_true', default=False,
    )
    args.add_argument(
        '--filter-label',
        help='Only include issues with this label in the output. Multiple '
             'invocations of this flag will require the issue to have all '
             ' labels.',
        action='append', dest='filter_labels', default=[],
    )
    args.add_argument(
        'repository',
        help='Repository to retrieve issues from (e.g., rcbops/rpc-openstack)',
    )
    return args


def get_repo(owner, name, token, cache_path='~/.gh2/cache'):
    cache_path = os.path.expanduser(cache_path)

    gh = github3.GitHub(token=token)
    gh.session = cachecontrol.CacheControl(
        gh.session, cache=cachecontrol.caches.FileCache(cache_path)
    )
    return gh.repository(owner, name)


def issues_for(repository, state):
    return repository.issues(state=state, direction='asc')


def label_events_for(issue):
    if not issue.labels:
        return []
    return ((event.label['name'], event) for event in issue.events()
            if event.event == 'labeled')


def issue_to_dict(fields, issue, additional_labels):
    retrievers = fields_to_callables(fields)
    base_attributes = (retriever(issue) for retriever in retrievers)
    issue_labels = list(issue.labels())
    label_attributes = (label in issue_labels for label in additional_labels)
    attributes = itertools.chain(base_attributes, label_attributes)
    return collections.OrderedDict(
        (field, attr.encode('utf-8') if hasattr(attr, 'encode') else attr)
        for field, attr in zip(itertools.chain(fields, additional_labels),
                               attributes)
    )


def field_to_callable(field):
    attrs = field.split(':')
    if len(attrs) > 1 and attrs[0] == 'label':
        label_name = attrs[1]
        attribute = attrs[2]

        def retriever(issue):
            for label, event in label_events_for(issue):
                if label_name == label:
                    return getattr(event, attribute, None)
    elif attrs[0] == 'Milestone':
        def retriever(issue):
            return getattr(issue.milestone, 'title', 'No Milestone')
    else:
        def retriever(issue):
            return getattr(issue, field, None)
    return retriever


def fields_to_callables(fields):
    return [field_to_callable(field) for field in fields]


def format_dates(attributes, fmt):
    return [
        attr.strftime(fmt) if hasattr(attr, 'strftime') else attr
        for attr in attributes
    ]


def is_pull_request(issue):
    pr = issue.as_dict().get('pull_request')
    return pr and isinstance(pr, dict)


def normalize_sequential_dates(issue_list):
    """Adjust issue status dates based on latest state.

    issue_list must contain a contiguous set of items that represent dates.
    None is an exceptable date in this situation. These dates must start with
    created_at and finish with closed_at. This function searches issue_list for
    the dates and then modifies them such that older dates always preceed
    newer dates when viewed from created_at to closed_at.
    """
    start, finish = ('created_at', 'closed_at')
    date_fields = []
    for field in issue_list:
        if field == start:
            date_fields.append(field)
            continue
        elif not date_fields:
            continue
        else:
            date_fields.append(field)
        if field == finish:
            break

    number_of_dates = len(date_fields) - 1
    # We need to work backwards
    i = 0
    while i < number_of_dates:
        date = issue_list[date_fields[i]]
        filtered_dates = filter(None,
                                (issue_list[f] for f in date_fields[i + 1:]))
        if not filtered_dates:
            # If everything after this date is None, there's no need to keep
            # looping
            break
        next_earliest_date = min(filtered_dates)
        if date is not None and date > next_earliest_date:
            issue_list[date_fields[i]] = next_earliest_date
        i += 1

    return issue_list


def write_rows(filename, headers, fields, issues, date_format, include_prs,
               skip_normalization, additional_labels, filter_labels=None):
    with open(filename, 'w') as fd:
        writer = csv.writer(fd)
        writer.writerow(headers)
        if filter_labels:
            filter_labels = set(filter_labels)
        for issue in issues:
            if not include_prs and is_pull_request(issue):
                continue
            issue_labels = {l.name for l in issue.labels()}
            if filter_labels and not filter_labels.issubset(issue_labels):
                continue
            issue_data = issue_to_dict(fields, issue, additional_labels)
            if not skip_normalization:
                issue_data = normalize_sequential_dates(issue_data)
            writer.writerow(format_dates(issue_data.values(), date_format))


def set_headers(repo, labels=None):
    headers = [
        'ID', 'Link', 'Name', 'Backlog', 'Triage', 'Investigate', 'Approved',
        'Doing', 'Needs Review (Ready)', 'Needs Review (Doing)',
        'Backport (Ready)', 'Backport (Doing)', 'Documentation (Ready)',
        'Documentation (Doing)', 'Pending SHA Update', 'Dev Done',
        'Milestone'
    ]
    if labels:
        headers.extend('Label: ' + label.name for label in labels)
    return headers


def main():
    parser = make_parser()
    token = os.environ.get('GITHUB_TOKEN')
    if token is None:
        parser.exit(status=1,
                    message='No GITHUB_TOKEN specified by the user\n')
    args = parser.parse_args()

    repo_owner, repo_name = args.repository.split('/', 1)
    repo = get_repo(repo_owner, repo_name, token)

    if args.include_labels:
        additional_labels = sorted((label for label in repo.labels()),
                                   key=lambda l: l.name)
    else:
        additional_labels = []

    headers = set_headers(repo, additional_labels)
    fields = [
        'number',
        'html_url',
        'title',
        'created_at',
        'label:status-triage:created_at',
        'label:status-investigate:created_at',
        'label:status-approved:created_at',
        'label:status-doing:created_at',
        'label:status-needs-review-ready:created_at',
        'label:status-needs-review-doing:created_at',
        'label:status-needs-backport-ready:created_at',
        'label:status-needs-backport-doing:created_at',
        'label:status-needs-documentation-ready:created_at',
        'label:status-needs-documentation-doing:created_at',
        'label:status-pending-sha-update:created_at',
        'closed_at',
        'Milestone'
    ]

    write_rows(
        filename=args.output_file,
        headers=headers,
        fields=fields,
        issues=issues_for(repo, state=args.issue_state),
        date_format=args.date_format,
        include_prs=args.include_pull_requests,
        skip_normalization=args.skip_date_normalization,
        additional_labels=additional_labels,
        filter_labels=args.filter_labels
    )
