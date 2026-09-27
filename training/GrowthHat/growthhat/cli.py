"""Command-line interface for GrowthHat."""

import argparse
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .models import Source, Audience, Offer, Hypothesis, Test, EvidenceType, Outcome
from .repository import Repository


DEFAULT_DB_PATH = Path.home() / ".growthhat.db"


def get_repository(db_path: Optional[str] = None) -> Repository:
    """Get repository instance with given or default path."""
    path = db_path if db_path else str(DEFAULT_DB_PATH)
    return Repository(path)


def cmd_source_add(args, repo: Repository) -> int:
    """Handle 'source add' command."""
    evidence = EvidenceType.ASSUMED
    if args.evidence_type:
        try:
            evidence = EvidenceType(args.evidence_type)
        except ValueError:
            print(f"Error: Invalid evidence type '{args.evidence_type}'. "
                  f"Valid options: measured, proposed, assumed", file=sys.stderr)
            return 1

    source = Source(
        name=args.name,
        source_type=args.type or "",
        url=args.url,
        notes=args.notes or "",
        evidence_type=evidence,
    )
    repo.create(source)
    print(f"Created source: {source.id}")
    print(f"  Name: {source.name}")
    if source.url:
        print(f"  URL: {source.url}")
    return 0


def cmd_source_list(args, repo: Repository) -> int:
    """Handle 'source list' command."""
    sources = repo.list_all(Source)
    if not sources:
        print("No sources found.")
        return 0

    print(f"{'ID':<38} {'Name':<30} {'Type':<15} {'Evidence'}")
    print("-" * 95)
    for s in sources:
        name_display = s.name[:28] + ".." if len(s.name) > 30 else s.name
        type_display = s.source_type[:13] + ".." if len(s.source_type) > 15 else s.source_type
        print(f"{s.id:<38} {name_display:<30} {type_display:<15} {s.evidence_type.value}")
    print(f"\nTotal: {len(sources)} source(s)")
    return 0


def cmd_source_show(args, repo: Repository) -> int:
    """Handle 'source show' command."""
    source = repo.get(Source, args.id)
    if source is None:
        print(f"Error: Source with ID '{args.id}' not found.", file=sys.stderr)
        return 1

    print(f"Source: {source.id}")
    print(f"  Name:          {source.name}")
    print(f"  Type:          {source.source_type or '(none)'}")
    print(f"  URL:           {source.url or '(none)'}")
    print(f"  Notes:         {source.notes or '(none)'}")
    print(f"  Evidence Type: {source.evidence_type.value}")
    print(f"  Created:       {source.created_at}")
    print(f"  Updated:       {source.updated_at}")
    return 0


def cmd_audience_add(args, repo: Repository) -> int:
    """Handle 'audience add' command."""
    evidence = EvidenceType.ASSUMED
    if args.evidence_type:
        try:
            evidence = EvidenceType(args.evidence_type)
        except ValueError:
            print(f"Error: Invalid evidence type '{args.evidence_type}'. "
                  f"Valid options: measured, proposed, assumed", file=sys.stderr)
            return 1

    audience = Audience(
        name=args.name,
        description=args.description or "",
        needs=args.needs or "",
        objections=args.objections or "",
        discovery_channels=args.channels or "",
        evidence_type=evidence,
    )
    repo.create(audience)
    print(f"Created audience: {audience.id}")
    print(f"  Name: {audience.name}")
    if audience.description:
        print(f"  Description: {audience.description}")
    return 0


def cmd_audience_list(args, repo: Repository) -> int:
    """Handle 'audience list' command."""
    audiences = repo.list_all(Audience)
    if not audiences:
        print("No audiences found.")
        return 0

    print(f"{'ID':<38} {'Name':<30} {'Evidence'}")
    print("-" * 80)
    for a in audiences:
        name_display = a.name[:28] + ".." if len(a.name) > 30 else a.name
        print(f"{a.id:<38} {name_display:<30} {a.evidence_type.value}")
    print(f"\nTotal: {len(audiences)} audience(s)")
    return 0


def cmd_offer_add(args, repo: Repository) -> int:
    """Handle 'offer add' command."""
    evidence = EvidenceType.ASSUMED
    if args.evidence_type:
        try:
            evidence = EvidenceType(args.evidence_type)
        except ValueError:
            print(f"Error: Invalid evidence type '{args.evidence_type}'. "
                  f"Valid options: measured, proposed, assumed", file=sys.stderr)
            return 1

    # Validate audience_id if provided
    if args.audience_id:
        audience = repo.get(Audience, args.audience_id)
        if audience is None:
            print(f"Error: Audience with ID '{args.audience_id}' not found.", file=sys.stderr)
            return 1

    offer = Offer(
        name=args.name,
        description=args.description or "",
        value_proposition=args.value or "",
        audience_id=args.audience_id,
        evidence_type=evidence,
    )
    repo.create(offer)
    print(f"Created offer: {offer.id}")
    print(f"  Name: {offer.name}")
    if offer.value_proposition:
        print(f"  Value: {offer.value_proposition}")
    return 0


def cmd_offer_list(args, repo: Repository) -> int:
    """Handle 'offer list' command."""
    offers = repo.list_all(Offer)
    if not offers:
        print("No offers found.")
        return 0

    print(f"{'ID':<38} {'Name':<30} {'Evidence'}")
    print("-" * 80)
    for o in offers:
        name_display = o.name[:28] + ".." if len(o.name) > 30 else o.name
        print(f"{o.id:<38} {name_display:<30} {o.evidence_type.value}")
    print(f"\nTotal: {len(offers)} offer(s)")
    return 0


def cmd_test_add(args, repo: Repository) -> int:
    """Handle 'test add' command."""
    hypothesis = repo.get(Hypothesis, args.hypothesis_id)
    if hypothesis is None:
        print(f"Error: Hypothesis with ID '{args.hypothesis_id}' not found.", file=sys.stderr)
        return 1

    test = Test(
        hypothesis_id=args.hypothesis_id,
        name=args.name or "",
        method=args.method or "",
        success_criteria=args.success_criteria or "",
    )
    repo.create(test)
    print(f"Created test: {test.id}")
    print(f"  Hypothesis: {test.hypothesis_id}")
    if test.name:
        print(f"  Name: {test.name}")
    if test.method:
        print(f"  Method: {test.method}")
    if test.success_criteria:
        print(f"  Success criteria: {test.success_criteria}")
    return 0


def cmd_test_list(args, repo: Repository) -> int:
    """Handle 'test list' command."""
    tests = repo.list_all(Test)
    if not tests:
        print("No tests found.")
        return 0

    print(f"{'ID':<38} {'Hypothesis ID':<38} {'Name':<30} {'Status'}")
    print("-" * 120)
    for t in tests:
        name_display = t.name[:28] + ".." if len(t.name) > 30 else t.name
        print(f"{t.id:<38} {t.hypothesis_id:<38} {name_display:<30} {t.status}")
    print(f"\nTotal: {len(tests)} test(s)")
    return 0


def cmd_outcome_add(args, repo: Repository) -> int:
    """Handle 'outcome add' command."""
    test = repo.get(Test, args.test_id)
    if test is None:
        print(f"Error: Test with ID '{args.test_id}' not found.", file=sys.stderr)
        return 1

    if args.confidence is not None:
        if not math.isfinite(args.confidence) or args.confidence < 0 or args.confidence > 1:
            print(f"Error: Confidence must be a finite value between 0 and 1, got '{args.confidence}'.", file=sys.stderr)
            return 1

    sh = None
    if args.supports_hypothesis:
        if args.supports_hypothesis == 'yes':
            sh = True
        elif args.supports_hypothesis == 'no':
            sh = False

    outcome = Outcome(
        test_id=args.test_id,
        result=args.result,
        supports_hypothesis=sh,
        confidence=args.confidence,
        metrics=args.metrics or "",
        interpretation=args.interpretation or "",
    )
    repo.create(outcome)
    print(f"Created outcome: {outcome.id}")
    print(f"  Test ID: {outcome.test_id}")
    print(f"  Result: {outcome.result}")
    supports_text = 'None' if outcome.supports_hypothesis is None else str(outcome.supports_hypothesis)
    print(f"  Supports hypothesis: {supports_text}")
    if outcome.confidence is not None:
        print(f"  Confidence: {outcome.confidence}")
    if outcome.metrics:
        print(f"  Metrics: {outcome.metrics}")
    if outcome.interpretation:
        print(f"  Interpretation: {outcome.interpretation}")
    return 0


def cmd_outcome_list(args, repo: Repository) -> int:
    """Handle 'outcome list' command."""
    outcomes = repo.list_all(Outcome)
    if not outcomes:
        print("No outcomes found.")
        return 0

    for o in outcomes:
        supports_text = 'None' if o.supports_hypothesis is None else str(o.supports_hypothesis)
        confidence_text = str(o.confidence) if o.confidence is not None else 'None'
        print(f"Outcome: {o.id}")
        print(f"  Test ID: {o.test_id}")
        print(f"  Supports hypothesis: {supports_text}")
        print(f"  Confidence: {confidence_text}")
        if o.metrics:
            print(f"  Metrics: {o.metrics}")
        print(f"  Result: {o.result}")
        if o.interpretation:
            print(f"  Interpretation: {o.interpretation}")
    print(f"\nTotal: {len(outcomes)} outcome(s)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser."""
    parser = argparse.ArgumentParser(
        prog="growthhat",
        description="GrowthHat: Evidence-driven audience/offer/journey research workbench",
    )
    parser.add_argument(
        "--db",
        metavar="PATH",
        help=f"Database file path (default: {DEFAULT_DB_PATH})",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # source command
    source_parser = subparsers.add_parser("source", help="Manage research sources")
    source_subparsers = source_parser.add_subparsers(dest="source_command", help="Source commands")

    # source add
    add_parser = source_subparsers.add_parser("add", help="Add a new source")
    add_parser.add_argument("--name", "-n", required=True, help="Source name/title")
    add_parser.add_argument("--url", "-u", help="URL or reference")
    add_parser.add_argument("--type", "-t", help="Source type (interview, survey, article, analytics, etc.)")
    add_parser.add_argument("--notes", help="Notes about this source")
    add_parser.add_argument("--evidence-type", "-e", choices=["measured", "proposed", "assumed"],
                           help="Evidence classification (default: assumed)")

    # source list
    source_subparsers.add_parser("list", help="List all sources")

    # source show
    show_parser = source_subparsers.add_parser("show", help="Show source details")
    show_parser.add_argument("id", help="Source ID to show")

    # audience command
    audience_parser = subparsers.add_parser("audience", help="Manage target audiences")
    audience_subparsers = audience_parser.add_subparsers(dest="audience_command", help="Audience commands")

    # audience add
    aud_add_parser = audience_subparsers.add_parser("add", help="Add a new audience")
    aud_add_parser.add_argument("--name", "-n", required=True, help="Audience name")
    aud_add_parser.add_argument("--description", "-d", help="Audience description")
    aud_add_parser.add_argument("--needs", help="What they need")
    aud_add_parser.add_argument("--objections", help="Common objections")
    aud_add_parser.add_argument("--channels", help="Discovery channels")
    aud_add_parser.add_argument("--evidence-type", "-e", choices=["measured", "proposed", "assumed"],
                               help="Evidence classification (default: assumed)")

    # audience list
    audience_subparsers.add_parser("list", help="List all audiences")

    # offer command
    offer_parser = subparsers.add_parser("offer", help="Manage offers")
    offer_subparsers = offer_parser.add_subparsers(dest="offer_command", help="Offer commands")

    # offer add
    off_add_parser = offer_subparsers.add_parser("add", help="Add a new offer")
    off_add_parser.add_argument("--name", "-n", required=True, help="Offer name")
    off_add_parser.add_argument("--description", "-d", help="Offer description")
    off_add_parser.add_argument("--value", "-v", help="Value proposition")
    off_add_parser.add_argument("--audience-id", "-a", help="Target audience ID")
    off_add_parser.add_argument("--evidence-type", "-e", choices=["measured", "proposed", "assumed"],
                               help="Evidence classification (default: assumed)")

    # offer list
    offer_subparsers.add_parser("list", help="List all offers")

    # hypothesis command
    hyp_parser = subparsers.add_parser("hypothesis", help="Manage hypotheses")
    hyp_subparsers = hyp_parser.add_subparsers(dest="hypothesis_command", help="Hypothesis commands")

    # hypothesis add
    hyp_add_parser = hyp_subparsers.add_parser("add", help="Add a new hypothesis")
    hyp_add_parser.add_argument("--statement", required=True, help="Hypothesis statement")
    hyp_add_parser.add_argument("--evidence-type", required=True, choices=["measured", "proposed", "assumed"],
                               help="Evidence classification")
    hyp_add_parser.add_argument("--source-id", help="Source ID")
    hyp_add_parser.add_argument("--audience-id", help="Audience ID")
    hyp_add_parser.add_argument("--offer-id", help="Offer ID")
    hyp_add_parser.add_argument("--rationale", help="Rationale for the hypothesis")

    # hypothesis list
    hyp_subparsers.add_parser("list", help="List all hypotheses")

    # test command
    test_parser = subparsers.add_parser("test", help="Manage hypothesis tests")
    test_subparsers = test_parser.add_subparsers(dest="test_command", help="Test commands")

    # test add
    test_add_parser = test_subparsers.add_parser("add", help="Add a new test for a hypothesis")
    test_add_parser.add_argument("--hypothesis-id", required=True, help="Parent hypothesis ID")
    test_add_parser.add_argument("--name", "-n", help="Test name")
    test_add_parser.add_argument("--method", "-m", help="How the test is conducted")
    test_add_parser.add_argument("--success-criteria", "-s", help="What counts as success")

    # test list
    test_subparsers.add_parser("list", help="List all tests")

    # outcome command
    outcome_parser = subparsers.add_parser("outcome", help="Manage test outcomes")
    outcome_subparsers = outcome_parser.add_subparsers(dest="outcome_command", help="Outcome commands")

    # outcome add
    outcome_add_parser = outcome_subparsers.add_parser("add", help="Add a new outcome")
    outcome_add_parser.add_argument("--test-id", required=True, help="Test ID to associate")
    outcome_add_parser.add_argument("--result", required=True, help="Outcome result text")
    outcome_add_parser.add_argument("--supports-hypothesis", choices=["yes", "no", "unknown"],
                                    help="Does the outcome support the hypothesis?")
    outcome_add_parser.add_argument("--confidence", type=float, help="Confidence level 0..1")
    outcome_add_parser.add_argument("--metrics", help="Quantitative metrics if any")
    outcome_add_parser.add_argument("--interpretation", help="Interpretation of the result")

    # outcome list
    outcome_subparsers.add_parser("list", help="List all outcomes")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Main entry point for CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "source":
        if args.source_command is None:
            parser.parse_args(["source", "--help"])
            return 0

        repo = get_repository(args.db)
        try:
            if args.source_command == "add":
                return cmd_source_add(args, repo)
            elif args.source_command == "list":
                return cmd_source_list(args, repo)
            elif args.source_command == "show":
                return cmd_source_show(args, repo)
        finally:
            repo.close()

    elif args.command == "audience":
        if args.audience_command is None:
            parser.parse_args(["audience", "--help"])
            return 0

        repo = get_repository(args.db)
        try:
            if args.audience_command == "add":
                return cmd_audience_add(args, repo)
            elif args.audience_command == "list":
                return cmd_audience_list(args, repo)
        finally:
            repo.close()

    elif args.command == "offer":
        if args.offer_command is None:
            parser.parse_args(["offer", "--help"])
            return 0

        repo = get_repository(args.db)
        try:
            if args.offer_command == "add":
                return cmd_offer_add(args, repo)
            elif args.offer_command == "list":
                return cmd_offer_list(args, repo)
        finally:
            repo.close()

    elif args.command == "hypothesis":
        if args.hypothesis_command is None:
            parser.parse_args(["hypothesis", "--help"])
            return 0

        repo = get_repository(args.db)
        try:
            if args.hypothesis_command == "add":
                from .models import Hypothesis
                if args.source_id and repo.get(Source, args.source_id) is None:
                    print(f"Error: Source ID '{args.source_id}' not found.", file=sys.stderr)
                    return 1
                if args.audience_id and repo.get(Audience, args.audience_id) is None:
                    print(f"Error: Audience ID '{args.audience_id}' not found.", file=sys.stderr)
                    return 1
                if args.offer_id and repo.get(Offer, args.offer_id) is None:
                    print(f"Error: Offer ID '{args.offer_id}' not found.", file=sys.stderr)
                    return 1
                hyp = Hypothesis(
                    statement=args.statement,
                    evidence_type=EvidenceType(args.evidence_type),
                    source_id=args.source_id,
                    audience_id=args.audience_id,
                    offer_id=args.offer_id,
                    rationale=args.rationale or ""
                )
                repo.create(hyp)
                print(f"Created hypothesis: {hyp.id}")
                return 0
            elif args.hypothesis_command == "list":
                from .models import Hypothesis
                hypotheses = repo.list_all(Hypothesis)
                if not hypotheses:
                    print("No hypotheses found.")
                    return 0
                print(f"{'ID':<38} {'Statement':<30} {'Source':<38} {'Audience':<38} {'Offer':<38} {'Evidence'}")
                print("-" * 220)
                for h in hypotheses:
                    stmt = (h.statement[:27] + "..") if len(h.statement) > 30 else h.statement
                    src_id = h.source_id if h.source_id else "None"
                    aud_id = h.audience_id if h.audience_id else "None"
                    off_id = h.offer_id if h.offer_id else "None"
                    print(f"{h.id:<38} {stmt:<30} {src_id:<38} {aud_id:<38} {off_id:<38} {h.evidence_type.value}")
                    if h.rationale:
                        print(f"    Rationale: {h.rationale}")
                print(f"\nTotal: {len(hypotheses)} hypothesis(es)")
                return 0
        finally:
            repo.close()

    elif args.command == "test":
        if args.test_command is None:
            parser.parse_args(["test", "--help"])
            return 0

        repo = get_repository(args.db)
        try:
            if args.test_command == "add":
                return cmd_test_add(args, repo)
            elif args.test_command == "list":
                return cmd_test_list(args, repo)
        finally:
            repo.close()

    elif args.command == "outcome":
        if args.outcome_command is None:
            parser.parse_args(["outcome", "--help"])
            return 0

        repo = get_repository(args.db)
        try:
            if args.outcome_command == "add":
                return cmd_outcome_add(args, repo)
            elif args.outcome_command == "list":
                return cmd_outcome_list(args, repo)
        finally:
            repo.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
