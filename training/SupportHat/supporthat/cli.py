"""Command-line interface for SupportHat case management."""

import argparse
import json
import sys
from pathlib import Path

from . import db
from . import documents
from . import drafts
from . import metrics
from . import search


def format_case(case, verbose=False):
    """Format a case for display."""
    if verbose:
        lines = [
            f"Case #{case['id']}",
            f"  Subject:     {case['subject']}",
            f"  Status:      {case['status']}",
            f"  Priority:    {case['priority']}",
            f"  Source:      {case['source'] or '-'}",
            f"  Assignee:    {case['assignee'] or '-'}",
            f"  Created:     {case['created_at']}",
            f"  Updated:     {case['updated_at']}",
        ]
        if case.get('description'):
            lines.append(f"  Description: {case['description']}")
        return '\n'.join(lines)
    else:
        return f"#{case['id']:4d} [{case['status']:11s}] [{case['priority']:6s}] {case['subject'][:50]}"


def cmd_create(args, conn):
    """Handle create-case command."""
    case_id = db.create_case(
        conn,
        subject=args.subject,
        description=args.description,
        priority=args.priority,
        source=args.source,
        assignee=args.assignee
    )
    if args.json:
        print(json.dumps({"id": case_id, "status": "created"}))
    else:
        print(f"Created case #{case_id}")
    return 0


def cmd_list(args, conn):
    """Handle list-cases command."""
    cases = db.list_cases(
        conn,
        status=args.status,
        assignee=args.assignee,
        limit=args.limit
    )
    if args.json:
        print(json.dumps(cases, indent=2))
    elif not cases:
        print("No cases found.")
    else:
        for case in cases:
            print(format_case(case))
    return 0


def cmd_show(args, conn):
    """Handle show-case command."""
    case = db.get_case(conn, args.id)
    if case is None:
        print(f"Case #{args.id} not found.", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(case, indent=2))
    else:
        print(format_case(case, verbose=True))
    return 0


def cmd_update(args, conn):
    """Handle update-case command."""
    fields = {}
    if args.status:
        fields['status'] = args.status
    if args.priority:
        fields['priority'] = args.priority
    if args.assignee is not None:
        fields['assignee'] = args.assignee if args.assignee != '' else None
    if args.subject:
        fields['subject'] = args.subject
    
    if not fields:
        print("No updates specified.", file=sys.stderr)
        return 1
    
    success = db.update_case(conn, args.id, **fields)
    if not success:
        print(f"Case #{args.id} not found.", file=sys.stderr)
        return 1
    
    if args.json:
        print(json.dumps({"id": args.id, "status": "updated"}))
    else:
        print(f"Updated case #{args.id}")
    return 0


def cmd_triage(args, conn):
    """Handle triage command."""
    success = db.triage_case(
        conn,
        args.id,
        priority=args.priority,
        assignee=args.assignee,
        note=args.note,
        changed_by=args.by
    )
    if not success:
        print(f"Case #{args.id} not found.", file=sys.stderr)
        return 1
    
    if args.json:
        print(json.dumps({"id": args.id, "status": "triaged"}))
    else:
        print(f"Triaged case #{args.id}")
    return 0


def cmd_transition(args, conn):
    """Handle transition command."""
    try:
        success = db.transition_status(
            conn,
            args.id,
            args.to,
            changed_by=args.by,
            note=args.note
        )
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1
    
    if not success:
        print(f"Case #{args.id} not found.", file=sys.stderr)
        return 1
    
    if args.json:
        print(json.dumps({"id": args.id, "new_status": args.to}))
    else:
        print(f"Transitioned case #{args.id} to {args.to}")
    return 0


def cmd_history(args, conn):
    """Handle history command."""
    case = db.get_case(conn, args.id)
    if case is None:
        print(f"Case #{args.id} not found.", file=sys.stderr)
        return 1
    
    history = db.get_status_history(conn, args.id)
    if args.json:
        print(json.dumps(history, indent=2))
    elif not history:
        print("No status history found.")
    else:
        print(f"Status history for case #{args.id}:")
        for entry in history:
            old = entry['old_status'] or '(created)'
            by = f" by {entry['changed_by']}" if entry['changed_by'] else ""
            note = f" - {entry['note']}" if entry['note'] else ""
            print(f"  {entry['changed_at']}: {old} -> {entry['new_status']}{by}{note}")
    return 0


def cmd_add_note(args, conn):
    """Handle add-note command."""
    note_id = db.add_note(conn, args.id, args.content, author=args.author)
    if note_id is None:
        print(f"Case #{args.id} not found.", file=sys.stderr)
        return 1
    
    if args.json:
        print(json.dumps({"note_id": note_id, "case_id": args.id}))
    else:
        print(f"Added note #{note_id} to case #{args.id}")
    return 0


def cmd_notes(args, conn):
    """Handle notes command."""
    case = db.get_case(conn, args.id)
    if case is None:
        print(f"Case #{args.id} not found.", file=sys.stderr)
        return 1
    
    notes = db.get_notes(conn, args.id)
    if args.json:
        print(json.dumps(notes, indent=2))
    elif not notes:
        print("No notes found.")
    else:
        print(f"Notes for case #{args.id}:")
        for note in notes:
            author = note['author'] or 'anonymous'
            print(f"  [{note['created_at']}] ({author}): {note['content']}")
    return 0


def cmd_ingest_docs(args, conn):
    """Handle ingest-docs command."""
    try:
        results = documents.ingest_directory(conn, args.directory)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1
    
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(f"Ingested: {results['ingested']} new documents")
        print(f"Skipped:  {results['skipped']} unchanged documents")
        if results['errors'] > 0:
            print(f"Errors:   {results['errors']}")
    return 0


def cmd_list_sources(args, conn):
    """Handle list-sources command."""
    sources = documents.list_sources(conn)
    if args.json:
        # Return stable format with id and path
        output = [{"id": s["id"], "path": s["path"]} for s in sources]
        print(json.dumps(output, indent=2))
    elif not sources:
        print("No documents indexed.")
    else:
        print("Indexed documents:")
        for src in sources:
            print(f"  [{src['id']:4d}] {src['path']}")
    return 0


def cmd_search(args, conn):
    """Handle search command."""
    query = ' '.join(args.query)
    results = search.search_documents(conn, query)
    if args.json:
        print(json.dumps(results))
    elif not results:
        print("No matching passages found.")
    else:
        for i, r in enumerate(results, 1):
            print(f"--- Result {i} ---")
            print(f"Source: {r['path']} (lines {r['line_start']}-{r['line_end']})")
            print(r['passage'])
            print()
    return 0


def cmd_draft_response(args, conn):
    """Handle draft-response command."""
    draft = drafts.create_draft(conn, args.id, query=args.query)
    if draft is None:
        print(f"Case #{args.id} not found.", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(draft, indent=2))
    else:
        print(f"Draft #{draft['id']} for case #{draft['case_id']}")
        print(f"Grounded: {'yes' if draft['grounded'] else 'no'}")
        print(draft['text'])
    return 0


def cmd_list_drafts(args, conn):
    """Handle list-drafts command."""
    case = db.get_case(conn, args.id)
    if case is None:
        print(f"Case #{args.id} not found.", file=sys.stderr)
        return 1
    records = drafts.list_drafts(conn, args.id)
    if args.json:
        print(json.dumps(records, indent=2))
    elif not records:
        print("No drafts found.")
    else:
        print(f"Drafts for case #{args.id}:")
        for d in records:
            grounded = 'grounded' if d['grounded'] else 'insufficient evidence'
            print(f"  [{d['id']:4d}] ({grounded}) {d['text'][:60]}")
    return 0


def cmd_record_handoff(args, conn):
    """Handle record-handoff command."""
    success = metrics.record_handoff(conn, args.case_id)
    if not success:
        print(f"Case #{args.case_id} not found.", file=sys.stderr)
        return 1
    
    count = metrics.get_handoff_count(conn, args.case_id)
    if args.json:
        print(json.dumps({"case_id": args.case_id, "handoffs": count}))
    else:
        print(f"Recorded handoff for case #{args.case_id}. Total handoffs: {count}")
    return 0


def cmd_record_feedback(args, conn):
    """Handle record-feedback command."""
    try:
        success = metrics.record_feedback(conn, args.case_id, args.rating)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1
    
    if not success:
        print(f"Case #{args.case_id} not found.", file=sys.stderr)
        return 1
    
    if args.json:
        print(json.dumps({"case_id": args.case_id, "rating": args.rating, "status": "recorded"}))
    else:
        print(f"Recorded feedback rating {args.rating} for case #{args.case_id}")
    return 0


def cmd_list_feedback(args, conn):
    """Handle list-feedback command."""
    case = db.get_case(conn, args.case_id)
    if case is None:
        print(f"Case #{args.case_id} not found.", file=sys.stderr)
        return 1
    
    feedback_list = metrics.list_feedback(conn, args.case_id)
    if args.json:
        print(json.dumps(feedback_list, indent=2))
    elif not feedback_list:
        print("No feedback found.")
    else:
        print(f"Feedback for case #{args.case_id}:")
        for f in feedback_list:
            print(f"  [{f['id']:4d}] Rating: {f['rating']} ({f['recorded_at']})")
    return 0


def cmd_metrics_summary(args, conn):
    """Handle metrics-summary command."""
    summary = metrics.get_metrics_summary(conn)
    if args.json:
        print(json.dumps(summary))
    else:
        print("Metrics Summary:")
        print(f"  Resolved cases:     {summary['resolved_count']}")
        print(f"  Total handoffs:     {summary['total_handoffs']}")
        print(f"  Unanswered cases:   {summary['unanswered_count']}")
        print(f"  Feedback count:     {summary['feedback_count']}")
        avg_rating = summary['average_rating']
        print(f"  Average rating:     {avg_rating:.2f}" if avg_rating else "  Average rating:     N/A")
        avg_res = summary['avg_resolution_time_seconds']
        print(f"  Avg resolution (s): {avg_res:.1f}" if avg_res else "  Avg resolution (s): N/A")
    return 0


def build_parser():
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        prog='supporthat',
        description='SupportHat - Local support ticket system for HatOS'
    )
    parser.add_argument('--db', type=Path, default=db.DEFAULT_DB_PATH,
                        help='Path to SQLite database file')
    parser.add_argument('--json', action='store_true',
                        help='Output in JSON format')
    
    subparsers = parser.add_subparsers(dest='command', required=True)
    
    # create-case
    create_p = subparsers.add_parser('create-case', help='Create a new support case')
    create_p.add_argument('subject', help='Case subject line')
    create_p.add_argument('-d', '--description', help='Detailed description')
    create_p.add_argument('-p', '--priority', default='normal',
                          choices=db.VALID_PRIORITIES, help='Case priority')
    create_p.add_argument('-s', '--source', help='Source of the case (email, chat, etc.)')
    create_p.add_argument('-a', '--assignee', help='Assigned team member')
    create_p.set_defaults(func=cmd_create)
    
    # list-cases
    list_p = subparsers.add_parser('list-cases', help='List support cases')
    list_p.add_argument('--status', choices=list(db.VALID_STATUSES) + ['open'], help='Filter by status')
    list_p.add_argument('--assignee', help='Filter by assignee')
    list_p.add_argument('--limit', type=int, default=50, help='Maximum cases to return')
    list_p.set_defaults(func=cmd_list)
    
    # show-case
    show_p = subparsers.add_parser('show-case', help='Show case details')
    show_p.add_argument('id', type=int, help='Case ID')
    show_p.set_defaults(func=cmd_show)
    
    # update-case
    update_p = subparsers.add_parser('update-case', help='Update a case')
    update_p.add_argument('id', type=int, help='Case ID')
    update_p.add_argument('--status', choices=db.VALID_STATUSES, help='New status')
    update_p.add_argument('--priority', choices=db.VALID_PRIORITIES, help='New priority')
    update_p.add_argument('--assignee', help='New assignee (empty string to clear)')
    update_p.add_argument('--subject', help='New subject')
    update_p.set_defaults(func=cmd_update)
    
    # triage
    triage_p = subparsers.add_parser('triage', help='Triage a case')
    triage_p.add_argument('id', type=int, help='Case ID')
    triage_p.add_argument('-p', '--priority', choices=db.VALID_PRIORITIES, help='Set priority')
    triage_p.add_argument('-a', '--assignee', help='Assign to team member')
    triage_p.add_argument('-n', '--note', help='Triage note')
    triage_p.add_argument('--by', help='Who is performing triage')
    triage_p.set_defaults(func=cmd_triage)
    
    # transition
    transition_p = subparsers.add_parser('transition', help='Transition case status')
    transition_p.add_argument('id', type=int, help='Case ID')
    transition_p.add_argument('--to', required=True, choices=db.VALID_STATUSES, help='Target status')
    transition_p.add_argument('-n', '--note', help='Transition note')
    transition_p.add_argument('--by', help='Who is performing transition')
    transition_p.set_defaults(func=cmd_transition)
    
    # history
    history_p = subparsers.add_parser('history', help='Show case status history')
    history_p.add_argument('id', type=int, help='Case ID')
    history_p.set_defaults(func=cmd_history)
    
    # add-note
    note_p = subparsers.add_parser('add-note', help='Add a note to a case')
    note_p.add_argument('id', type=int, help='Case ID')
    note_p.add_argument('content', help='Note content')
    note_p.add_argument('--author', help='Note author')
    note_p.set_defaults(func=cmd_add_note)
    
    # notes
    notes_p = subparsers.add_parser('notes', help='List notes for a case')
    notes_p.add_argument('id', type=int, help='Case ID')
    notes_p.set_defaults(func=cmd_notes)
    
    # ingest-docs
    ingest_p = subparsers.add_parser('ingest-docs', help='Ingest documents from a directory')
    ingest_p.add_argument('directory', help='Directory containing .txt/.md files')
    ingest_p.set_defaults(func=cmd_ingest_docs)
    
    # list-sources
    sources_p = subparsers.add_parser('list-sources', help='List indexed document sources')
    sources_p.set_defaults(func=cmd_list_sources)
    
    # search
    search_p = subparsers.add_parser('search', help='Search documents for relevant passages')
    search_p.add_argument('query', nargs='+', help='Search query terms')
    search_p.set_defaults(func=cmd_search)
    
    # draft-response
    draft_p = subparsers.add_parser('draft-response',
                                    help='Generate a grounded response draft for a case')
    draft_p.add_argument('id', type=int, metavar='CASE_ID', help='Case ID')
    draft_p.add_argument('--query',
                         help='Explicit search query (defaults to case subject/description)')
    draft_p.set_defaults(func=cmd_draft_response)
    
    # list-drafts
    drafts_p = subparsers.add_parser('list-drafts',
                                     help='List stored response drafts for a case')
    drafts_p.add_argument('id', type=int, metavar='CASE_ID', help='Case ID')
    drafts_p.set_defaults(func=cmd_list_drafts)
    
    # record-handoff
    handoff_p = subparsers.add_parser('record-handoff',
                                      help='Record a handoff for a case')
    handoff_p.add_argument('case_id', type=int, metavar='CASE_ID', help='Case ID')
    handoff_p.set_defaults(func=cmd_record_handoff)
    
    # record-feedback
    rec_fb_p = subparsers.add_parser('record-feedback',
                                     help='Record quality feedback for a case')
    rec_fb_p.add_argument('case_id', type=int, metavar='CASE_ID', help='Case ID')
    rec_fb_p.add_argument('--rating', type=int, required=True,
                          help='Quality rating (1-5)')
    rec_fb_p.set_defaults(func=cmd_record_feedback)
    
    # list-feedback
    list_fb_p = subparsers.add_parser('list-feedback',
                                      help='List feedback for a case')
    list_fb_p.add_argument('case_id', type=int, metavar='CASE_ID', help='Case ID')
    list_fb_p.set_defaults(func=cmd_list_feedback)
    
    # metrics-summary
    metrics_p = subparsers.add_parser('metrics-summary',
                                      help='Show metrics summary')
    metrics_p.set_defaults(func=cmd_metrics_summary)
    
    return parser


def main(argv=None):
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)
    
    conn = db.get_connection(args.db)
    try:
        return args.func(args, conn)
    finally:
        conn.close()


if __name__ == '__main__':
    sys.exit(main())
