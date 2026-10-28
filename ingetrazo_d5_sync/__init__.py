# SPDX-License-Identifier: GPL-3.0-or-later
"""D5 Sync — experimental live geometry and camera link to D5 Render.

Windows only. Requires installed D5 Render, Blender's compatible Python runtime
and D5 LiveSync for Blender. Blender does not run during synchronization.
"""
from .ingetrazo_d5_sync import setup, SyncController
