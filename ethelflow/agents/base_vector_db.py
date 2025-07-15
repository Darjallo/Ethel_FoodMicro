# Project Ethel
# Base for connecting to Chroma
#
# Copyright (C) 2025  Gerd Kortemeyer, ETH Zurich
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# agent_pool/base_vector_db.py

import os
from typing import Optional, Tuple, Any

from chromadb import PersistentClient


def sharded_path(collection_name: str) -> str:
    """
    Given a raw collection name (no tenant), return a sharded relative path:
        first_char/second_char/third_char/collection_name
    Pads with “_” if shorter than 3 chars.
    """
    padded = (collection_name + "___")[:3]
    first, second, third = padded[0], padded[1], padded[2]
    return os.path.join(first, second, third, collection_name)


def open_chroma_for(
    tenant: str, collection_name: str, emb_method: str
) -> Optional[Tuple[PersistentClient, Any]]:
    """
    Open (or create) a Chroma “default” collection under:

        CHROMA_BASE_DIR/
           └── <tenant>/
               └── <sharded_path(collection_name)>/
                   └── (Chroma files)

    Args:
      tenant         – your tenant code, e.g. “ethz”
      collection_name– your per-tenant collection, e.g. “course123”
      emb_method     – like “ada3large”

    Returns:
      (client, coll) on success, or None if an existing collection
      exists under a different emb_method or on error.
    """
    base_dir = os.getenv("CHROMA_BASE_DIR", "/chroma_db")
    # build the tenant-scoped shard folder
    folder = os.path.join(base_dir, tenant, sharded_path(collection_name))
    os.makedirs(folder, exist_ok=True)

    # init the Chroma client on that folder
    try:
        client = PersistentClient(path=folder)
    except Exception as e:
        print(f"[DEBUG] Could not open PersistentClient at {folder}: {e}", flush=True)
        return None

    # try to get or create the “default” collection with matching emb_method
    try:
        coll = client.get_collection("default")
        if coll.metadata.get("emb_method") == emb_method:
            return client, coll
        else:
            print(
                f"[DEBUG] Embedding‐method mismatch in {folder}: "
                f"found {coll.metadata.get('emb_method')}, expected {emb_method}",
                flush=True,
            )
            return None
    except Exception:
        # not found yet — create it
        try:
            coll = client.create_collection(
                name="default", metadata={"emb_method": emb_method}
            )
            return client, coll
        except Exception as e:
            print(f"[DEBUG] Failed to create ‘default’ in {folder}: {e}", flush=True)
            return None


def get_chroma_collection(tenant: str, collection_name: str) -> Optional[Any]:
    """
    Open the existing Chroma “default” collection for (tenant, collection_name),
    or return None if nothing exists or on error.
    """
    base_dir = os.getenv("CHROMA_BASE_DIR", "/chroma_db")
    folder = os.path.join(base_dir, tenant, sharded_path(collection_name))

    if not os.path.isdir(folder):
        return None

    try:
        client = PersistentClient(path=folder)
        return client.get_collection("default")
    except Exception:
        return None
