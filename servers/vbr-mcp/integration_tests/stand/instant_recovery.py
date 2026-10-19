# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""Instant Recovery (1.16): ``GET /api/v1/restore/instantRecovery/vSphere/vm``. Nothing is mounted at T0."""

from vbr_models.instant_recovery import InstantRecoveryMount

MOUNTS: list[InstantRecoveryMount] = []
"""The mounts; a case that starts or holds one adds it, with its ``/{id}`` route."""
