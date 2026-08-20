# -*- coding: utf-8 -*-
"""Migrate a single Folder content type to Document (in-place).

Usage:
    bin/rel_client run scripts/migrate_folder_to_document.py [options] /en/about/contact-us

    # Dry-run (default) — logs what would change, makes NO changes:
    bin/rel_client run scripts/migrate_folder_to_document.py /en/about/contact-us

    # Commit — actually perform the migration:
    bin/rel_client run scripts/migrate_folder_to_document.py --commit /en/about/contact-us

    # Inside a Docker container:
    docker exec <container> bin/rel_client run scripts/migrate_folder_to_document.py /en/about/contact-us

The path argument is relative to the Plone site root (e.g. /en/about/contact-us).

What it does:
    1. Traverses to the object at the given path
    2. Verifies it is portal_type == "Folder"
    3. Counts children (safety snapshot)
    4. Sets obj.portal_type = "Document"
    5. Calls migrate_base_class_to_new_class(obj) — changes __class__
       from plone.app.contenttypes.content.Folder to
       collective.folderishtypes.dx.content.FolderishDocument.
       Does NOT call _initBTrees (migrate_to_folderish=False),
       so child content is preserved.
    6. Full obj.reindexObject() (all indexes)
    7. Verifies children count unchanged
    8. Commits with a transaction note

Preserves: UID, path, editing history (CMFEditions), local roles,
           child content, Volto blocks, behaviors, workflow state.

Run in bottom-up order (leaf Folders first, parents last).
"""

import optparse
import sys
import transaction

from AccessControl.SecurityManagement import newSecurityManager
from AccessControl.SecurityManager import setSecurityPolicy
from Testing.makerequest import makerequest
from Products.CMFCore.tests.base.security import OmnipotentUser
from Products.CMFCore.tests.base.security import PermissiveSecurityPolicy

from plone.app.contenttypes.utils import migrate_base_class_to_new_class

version = "1.0.0"
usage = (
    "Usage: bin/rel_client run scripts/migrate_folder_to_document.py [options] "
    "<path-relative-to-plone-site>\n"
    "  e.g. bin/rel_client run scripts/migrate_folder_to_document.py /en/about/contact-us"
)
description = (
    "Migrate a single Folder to Document in-place. "
    "Dry-run by default; pass --commit to make changes. "
    "Run in bottom-up order (leaf Folders first, parents last)."
)

p = optparse.OptionParser(
    usage=usage,
    version="%prog " + version,
    description=description,
    prog="migrate_folder_to_document",
)
p.add_option(
    "--commit",
    action="store_true",
    dest="commit",
    default=False,
    help="Actually perform the migration. Without this flag, runs in dry-run mode.",
)
p.add_option(
    "--verbose",
    "-v",
    action="store_true",
    default=False,
    help="Show verbose output.",
)

# Parse arguments
args = sys.argv[1:]
# Strip the '-c script.py' prefix that zopectl adds
if len(args) >= 2 and args[0] == "-c" and args[1].endswith(".py"):
    args = args[2:]

options, positional = p.parse_args(args)

if not positional:
    print(p.print_help())
    sys.exit(1)

target_path = positional[0]

# Ensure leading slash
if not target_path.startswith("/"):
    target_path = "/" + target_path

try:
    app  # noqa
except NameError:
    print(p.print_help())
    sys.exit(1)


def spoof_request(app):
    """Set up a faux REQUEST and security context for the script."""
    _policy = PermissiveSecurityPolicy()
    setSecurityPolicy(_policy)
    newSecurityManager(None, OmnipotentUser().__of__(app.acl_users))
    return makerequest(app)


def find_plone_site(app):
    """Find the (first) Plone site in the ZODB root."""
    for site_id, site in app.items():
        if getattr(site, "meta_type", None) == "Plone Site":
            return site, site_id
    return None, None


def get_children_count(obj):
    """Count direct children of a container object."""
    try:
        return len(obj.objectIds())
    except Exception:
        return -1


def get_local_roles_snapshot(obj):
    """Get a snapshot of local roles for before/after comparison."""
    try:
        return dict(obj.__ac_local_roles__ or {})
    except Exception:
        return None


def get_blocks_info(obj):
    """Check if the object has Volto blocks."""
    has_blocks = hasattr(obj, "blocks") and bool(getattr(obj, "blocks", None))
    has_layout = hasattr(obj, "blocks_layout") and bool(
        getattr(obj, "blocks_layout", None)
    )
    block_count = 0
    if has_blocks and isinstance(obj.blocks, dict):
        block_count = len(obj.blocks)
    return has_blocks, has_layout, block_count


def main():
    # Enable faux request and security
    app_local = spoof_request(app)  # noqa

    site, site_id = find_plone_site(app_local)
    if site is None:
        print("ERROR: No Plone site found in ZODB root.")
        sys.exit(1)

    print(f"Plone site: {site_id}")
    print(f"Target path (relative to site): {target_path}")
    print(f"Mode: {'COMMIT' if options.commit else 'DRY-RUN (no changes will be made)'}")
    print("-" * 60)

    # Traverse to the object
    try:
        obj = site.unrestrictedTraverse(target_path)
    except Exception as e:
        print(f"ERROR: Could not traverse to '{target_path}': {e}")
        sys.exit(1)

    obj_path = "/".join(obj.getPhysicalPath())
    obj_uid = obj.UID()
    obj_portal_type = obj.portal_type
    obj_class = f"{obj.__class__.__module__}.{obj.__class__.__name__}"

    print(f"Object: {obj_path}")
    print(f"UID: {obj_uid}")
    print(f"Current portal_type: {obj_portal_type}")
    print(f"Current class: {obj_class}")

    # Verify it's a Folder
    if obj_portal_type != "Folder":
        print(f"SKIP: Object at '{target_path}' is '{obj_portal_type}', not 'Folder'.")
        if obj_portal_type == "Document":
            print("  Already migrated. Nothing to do.")
        sys.exit(0)

    # Gather before-state
    children_before = get_children_count(obj)
    local_roles_before = get_local_roles_snapshot(obj)
    has_blocks, has_layout, block_count = get_blocks_info(obj)

    # Get review_state
    review_state = "unknown"
    try:
        review_state = site.portal_workflow.getInfoFor(obj, "review_state")
    except Exception:
        pass

    print(f"Children count: {children_before}")
    print(f"Has blocks: {has_blocks} ({block_count} blocks)")
    print(f"Has blocks_layout: {has_layout}")
    print(f"Local roles: {local_roles_before}")
    print(f"Review state: {review_state}")
    print("-" * 60)

    if not options.commit:
        print("DRY-RUN: Would change:")
        print(f"  portal_type: 'Folder' -> 'Document'")
        print(
            "  class: 'plone.app.contenttypes.content.Folder' -> "
        )
        print(
            "         'collective.folderishtypes.dx.content.FolderishDocument'"
        )
        print("  Full reindex of all catalog indexes")
        print("  Transaction commit")
        print()
        print("To actually perform the migration, re-run with --commit")
        sys.exit(0)

    # --- COMMIT MODE ---
    print("Migrating...")

    # Step 1: Change portal_type
    obj.portal_type = "Document"
    print(f"  [OK] portal_type set to 'Document'")

    # Step 2: Change class via migrate_base_class_to_new_class
    # migrate_to_folderish=False (default) — does NOT call _initBTrees,
    # so children are preserved.
    try:
        result = migrate_base_class_to_new_class(obj)
    except Exception as e:
        print(f"  [FAIL] migrate_base_class_to_new_class failed: {e}")
        print("  Rolling back (no commit).")
        transaction.abort()
        sys.exit(1)

    if not result:
        print("  [FAIL] migrate_base_class_to_new_class returned False.")
        print("  Rolling back (no commit).")
        transaction.abort()
        sys.exit(1)

    new_class = f"{obj.__class__.__module__}.{obj.__class__.__name__}"
    print(f"  [OK] class changed to '{new_class}'")

    # Step 3: Full reindex
    obj.reindexObject()
    print("  [OK] reindexed (all indexes)")

    # Step 4: Verify children count unchanged
    children_after = get_children_count(obj)
    if children_after != children_before:
        print(
            f"  [FAIL] Children count changed: {children_before} -> {children_after}"
        )
        print("  Rolling back (no commit).")
        transaction.abort()
        sys.exit(1)
    print(f"  [OK] children count unchanged: {children_after}")

    # Step 5: Verify local roles preserved
    local_roles_after = get_local_roles_snapshot(obj)
    if local_roles_after != local_roles_before:
        print("  [WARNING] Local roles changed during migration!")
        print(f"    Before: {local_roles_before}")
        print(f"    After:  {local_roles_after}")
    else:
        print("  [OK] local roles preserved")

    # Step 6: Verify review_state preserved
    review_state_after = "unknown"
    try:
        review_state_after = site.portal_workflow.getInfoFor(obj, "review_state")
    except Exception:
        pass
    if review_state_after != review_state:
        print(
            f"  [WARNING] review_state changed: {review_state} -> {review_state_after}"
        )
    else:
        print(f"  [OK] review_state preserved: {review_state_after}")

    # Step 7: Verify blocks preserved
    has_blocks_after, has_layout_after, block_count_after = get_blocks_info(obj)
    if block_count_after != block_count:
        print(
            f"  [WARNING] block count changed: {block_count} -> {block_count_after}"
        )
    else:
        print(f"  [OK] blocks preserved: {block_count_after} blocks")

    # Step 8: Verify catalog brain shows correct portal_type
    catalog = site.portal_catalog
    brain = catalog.unrestrictedSearchResults(UID=obj_uid)
    if brain and len(brain) == 1:
        brain_portal_type = brain[0].portal_type
        if brain_portal_type == "Document":
            print(f"  [OK] catalog brain portal_type: 'Document'")
        else:
            print(
                f"  [WARNING] catalog brain portal_type is "
                f"'{brain_portal_type}', expected 'Document'"
            )
    else:
        print("  [WARNING] could not verify catalog brain")

    # Step 9: Commit
    note = f"Migrated Folder to Document: {obj_path}"
    tr = transaction.get()
    tr.note(note)
    transaction.commit()
    print(f"  [OK] committed: {note}")
    print("-" * 60)
    print("Migration complete.")
    print()
    print("After all Folders are migrated, consider removing the Folder FTI")
    print("from portal_types (separate step, not handled by this script).")


main()
sys.exit(0)
