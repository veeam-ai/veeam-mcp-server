# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

import json

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from pytest_httpx import HTTPXMock

from tests.conftest import tool_data

BASE = "https://localhost:9419"
MOUNT_PATH = "/api/v1/restore/instantRecovery/vSphere/vm"
RESTORE_POINT_ID = "00000000-0000-4000-8000-000000000014"
MOUNT_ID = "00000000-0000-4000-8000-000000000015"
HOST = {"hostName": "vc01.lab.local", "name": "esx01.lab.local", "type": "Host", "objectId": "host-12"}
DATASTORE = {"hostName": "vc01.lab.local", "name": "ds01", "type": "Datastore", "objectId": "datastore-7"}
NETWORK = {"hostName": "vc01.lab.local", "name": "VM Network", "type": "Network", "objectId": "network-9"}


def _add_token_response(httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE}/api/oauth2/token", json={"access_token": "t", "refresh_token": "r"})


async def test_start_instant_recovery_vsphere_vm_posts_the_mount_spec(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(url=f"{BASE}{MOUNT_PATH}", json={"id": "session-1"})

    result = await mcp_client.call_tool(
        "start_instant_recovery_vsphere_vm", {"restore_point_id": RESTORE_POINT_ID, "reason": "test"}
    )

    assert result.data == {"id": "session-1"}
    posted = next(r for r in httpx_mock.get_requests() if r.url.path == MOUNT_PATH and r.method == "POST")
    body = json.loads(posted.read())
    assert body["restorePointId"] == RESTORE_POINT_ID
    assert body["type"] == "OriginalLocation"
    assert body["reason"] == "test"
    assert body["secureRestore"] == {"antivirusScanEnabled": False, "yaraScanEnabled": False}


async def test_get_instant_recovery_mount_status_by_id(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(url=f"{BASE}{MOUNT_PATH}/{MOUNT_ID}", json={"id": MOUNT_ID, "state": "Mounted"})

    result = await mcp_client.call_tool("get_instant_recovery_mount_status", {"mount_id": MOUNT_ID})

    assert result.data == {"id": MOUNT_ID, "state": "Mounted"}


async def test_get_instant_recovery_mount_status_lists_by_vm_name(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(
        url=f"{BASE}{MOUNT_PATH}?vmNameFilter=fileserver01&skip=0&limit=200",
        json={"data": [{"id": MOUNT_ID, "vmName": "fileserver01"}], "pagination": {"total": 1}},
    )

    result = await mcp_client.call_tool("get_instant_recovery_mount_status", {"vm_name_filter": "fileserver01"})

    assert tool_data(result) == [{"id": MOUNT_ID, "vmName": "fileserver01"}]


async def test_unmount_instant_recovery_vsphere_vm(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(url=f"{BASE}{MOUNT_PATH}/{MOUNT_ID}/unmount", status_code=204)

    await mcp_client.call_tool("unmount_instant_recovery_vsphere_vm", {"mount_id": MOUNT_ID})

    posted = next(r for r in httpx_mock.get_requests() if r.url.path.endswith("/unmount"))
    assert posted.method == "POST"


async def test_restore_vsphere_vm_posts_the_restore_spec(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(url=f"{BASE}/api/v1/restore/vmRestore/vSphere", json={"id": "session-2"})

    result = await mcp_client.call_tool("restore_vsphere_vm", {"restore_point_id": RESTORE_POINT_ID, "overwrite": True})

    assert result.data == {"id": "session-2"}
    posted = next(r for r in httpx_mock.get_requests() if r.url.path == "/api/v1/restore/vmRestore/vSphere")
    body = json.loads(posted.read())
    assert body["overwrite"] is True
    assert body["type"] == "OriginalLocation"
    assert "quickRollback" not in body  # VBR's REST API ignores it for vSphere: every restore is a full one


async def test_restore_vsphere_vm_offers_no_quick_rollback(mcp_client: Client):
    tools = {tool.name: tool for tool in await mcp_client.list_tools()}

    assert "quick_rollback" not in tools["restore_vsphere_vm"].input_schema["properties"]


def _posted_body(httpx_mock: HTTPXMock, path: str) -> dict:
    return json.loads(next(r for r in httpx_mock.get_requests() if r.url.path == path and r.method == "POST").read())


async def test_start_instant_recovery_customized_posts_typed_placement(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(url=f"{BASE}{MOUNT_PATH}", json={"id": "session-1"})

    await mcp_client.call_tool(
        "start_instant_recovery_vsphere_vm",
        {
            "restore_point_id": RESTORE_POINT_ID,
            "mode": "Customized",
            "destination": {"restoredVmName": "web01-ir", "destinationHost": HOST},
            "datastore": {"redirectEnabled": True, "cacheDatastore": DATASTORE},
        },
    )

    body = _posted_body(httpx_mock, MOUNT_PATH)
    assert body["type"] == "Customized"
    assert body["destination"] == {"restoredVmName": "web01-ir", "destinationHost": {**HOST, "platform": "VSphere"}}
    assert body["datastore"] == {"redirectEnabled": True, "cacheDatastore": {**DATASTORE, "platform": "VSphere"}}


async def test_start_instant_recovery_customized_without_destination_host_is_rejected(mcp_client: Client):
    with pytest.raises(ToolError, match=r'mode="Customized" requires: destination.destinationHost'):
        await mcp_client.call_tool(
            "start_instant_recovery_vsphere_vm", {"restore_point_id": RESTORE_POINT_ID, "mode": "Customized"}
        )


async def test_start_instant_recovery_original_location_rejects_placement(mcp_client: Client):
    with pytest.raises(ToolError, match=r'mode="OriginalLocation" does not accept: datastore'):
        await mcp_client.call_tool(
            "start_instant_recovery_vsphere_vm",
            {"restore_point_id": RESTORE_POINT_ID, "datastore": {"redirectEnabled": False}},
        )


async def test_start_instant_recovery_rejects_unknown_nested_fields(mcp_client: Client):
    with pytest.raises(ToolError, match="restoredVmNam"):
        await mcp_client.call_tool(
            "start_instant_recovery_vsphere_vm",
            {
                "restore_point_id": RESTORE_POINT_ID,
                "mode": "Customized",
                "destination": {"restoredVmNam": "typo"},
                "datastore": {"redirectEnabled": False},
            },
        )


async def test_migrate_instant_recovery_posts_inventory_object_as_destination_host(
    mcp_client: Client, httpx_mock: HTTPXMock
):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(url=f"{BASE}{MOUNT_PATH}/{MOUNT_ID}/migrate", json={"id": "session-3"})

    await mcp_client.call_tool(
        "migrate_instant_recovery_vsphere_vm",
        {"mount_id": MOUNT_ID, "destination_host": HOST, "veeam_quick_migration_enabled": True},
    )

    body = _posted_body(httpx_mock, f"{MOUNT_PATH}/{MOUNT_ID}/migrate")
    assert body == {"destinationHost": {**HOST, "platform": "VSphere"}, "VeeamQMEnabled": True}


async def test_restore_file_share_posts_typed_destination(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    path = "/api/v1/restore/unstructuredData/fileShare"
    httpx_mock.add_response(url=f"{BASE}{path}", json={"id": "session-4"})
    server_id = "6a7b3f1e-2c3d-4e5f-8a9b-0c1d2e3f4a5b"

    await mcp_client.call_tool(
        "restore_file_share",
        {
            "restore_point_id": RESTORE_POINT_ID,
            "destination": {"unstructuredDataServerId": server_id, "path": "\\\\nas01\\restore"},
            "restore_options": {"overwriteMode": "ReplaceOlder", "restorePermissions": True},
        },
    )

    body = _posted_body(httpx_mock, path)
    assert body == {
        "restorePointId": RESTORE_POINT_ID,
        "destination": {"unstructuredDataServerId": server_id, "path": "\\\\nas01\\restore"},
        "restoreOptions": {"overwriteMode": "ReplaceOlder", "restorePermissions": True},
    }


async def test_restore_vsphere_vm_customized_posts_placement(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    path = "/api/v1/restore/vmRestore/vSphere"
    httpx_mock.add_response(url=f"{BASE}{path}", json={"id": "session-5"})

    await mcp_client.call_tool(
        "restore_vsphere_vm",
        {
            "restore_point_id": RESTORE_POINT_ID,
            "mode": "Customized",
            "destination_host": HOST,
            "datastore": {"defaultDatastore": DATASTORE},
            "network": {"networks": [{"sourceNetwork": NETWORK, "targetNetwork": NETWORK}]},
            "restore_proxies": {"autoSelectEnabled": True},
        },
    )

    body = _posted_body(httpx_mock, path)
    assert body["destinationHost"] == {**HOST, "platform": "VSphere"}
    assert body["datastore"] == {"defaultDatastore": {**DATASTORE, "platform": "VSphere"}}
    assert body["restoreProxies"] == {"autoSelectEnabled": True}


async def test_restore_vsphere_vm_original_location_rejects_placement(mcp_client: Client):
    with pytest.raises(ToolError, match=r"does not accept: destination_host"):
        await mcp_client.call_tool(
            "restore_vsphere_vm", {"restore_point_id": RESTORE_POINT_ID, "destination_host": HOST}
        )


async def test_restore_tools_publish_concrete_nested_schemas(mcp_client: Client):
    tools = {tool.name: tool for tool in await mcp_client.list_tools()}

    destination = tools["start_instant_recovery_vsphere_vm"].input_schema["properties"]["destination"]
    model = next(option for option in destination["anyOf"] if option.get("type") == "object")
    assert {"restoredVmName", "destinationHost", "folder", "resourcePool"} <= model["properties"].keys()

    host = tools["migrate_instant_recovery_vsphere_vm"].input_schema["properties"]["destination_host"]
    assert {"hostName", "name", "type"} <= set(host["required"])


async def test_restore_tool_schemas_stay_within_budget(mcp_client: Client):
    # FastMCP inlines every $ref, so each nested vSphere object is repeated in full; catch a model change that
    # balloons the tool list a client has to load into context.
    restore_tools = {
        "start_instant_recovery_vsphere_vm",
        "migrate_instant_recovery_vsphere_vm",
        "restore_file_share",
        "restore_object_storage",
        "restore_vsphere_vm",
    }
    sizes = {t.name: len(json.dumps(t.input_schema)) for t in await mcp_client.list_tools() if t.name in restore_tools}

    assert sizes.keys() == restore_tools
    assert all(size < 30_000 for size in sizes.values()), sizes


async def test_migrate_accepts_a_full_inventory_row_and_drops_response_only_fields(
    mcp_client: Client, httpx_mock: HTTPXMock
):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(url=f"{BASE}{MOUNT_PATH}/{MOUNT_ID}/migrate", json={"id": "session-6"})
    inventory_row = {**HOST, "platform": "VSphere", "size": "1.2 TB", "metadata": [{"field": "a", "data": "b"}]}

    await mcp_client.call_tool(
        "migrate_instant_recovery_vsphere_vm", {"mount_id": MOUNT_ID, "destination_host": inventory_row}
    )

    body = _posted_body(httpx_mock, f"{MOUNT_PATH}/{MOUNT_ID}/migrate")
    assert body == {"destinationHost": {**HOST, "platform": "VSphere"}}


# Inventory rows as VBR 13.1 returned them for a standalone ESXi host (lab), and the requests it accepted with them.
ESXI = "esx02.lab.local"
ESXI_HOST_ROW = {
    "type": "Host",
    "hostName": ESXI,
    "name": ESXI,
    "objectId": ESXI,
    "urn": f"esx:{ESXI}",
    "platform": "VSphere",
    "size": "17.2 TB",
}
ESXI_HA_HOST_ROW = {**ESXI_HOST_ROW, "objectId": "ha-host", "urn": f"esx:{ESXI};datacenter:ha-datacenter;esx:ha-host"}
RESOURCE_POOL_ROW = {
    "type": "ResourcePool",
    "hostName": ESXI,
    "name": "RP1",
    "objectId": "pool2",
    "platform": "VSphere",
}
DATACENTER_ROW = {
    "type": "Datacenter",
    "hostName": ESXI,
    "name": "ha-datacenter",
    "objectId": "ha-datacenter",
    "platform": "VSphere",
}
DATASTORE_ROW = {
    "type": "Datastore",
    "hostName": ESXI,
    "name": "ydd1",
    "objectId": "62225a70-7bb70406-feb2-3cecef88e5ec",
    "platform": "VSphere",
    "metadata": [{"field": "freeSpace", "data": "27.1 TB"}],
}
NETWORK_ROW = {
    "type": "Network",
    "hostName": ESXI,
    "name": "VM Network",
    "objectId": "VM Network",
    "platform": "VSphere",
}
# The same network as the restore point's `networkInfo` names it: its id is not the inventory objectId.
SOURCE_NETWORK_INFO = {"id": "192", "name": "VM Network"}


def _ref(row: dict) -> dict:
    """What a restore tool sends for an inventory row: its identifying fields only."""
    return {key: row[key] for key in ("platform", "type", "hostName", "name", "objectId", "urn") if key in row}


async def test_start_instant_recovery_customized_sends_the_lab_accepted_spec(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(url=f"{BASE}{MOUNT_PATH}", json={"id": MOUNT_ID})

    result = await mcp_client.call_tool(
        "start_instant_recovery_vsphere_vm",
        {
            "restore_point_id": RESTORE_POINT_ID,
            "mode": "Customized",
            "power_up": False,
            "nics_enabled": False,
            "destination": {
                "restoredVmName": "ydwin16vc-mcp-ir",
                "destinationHost": ESXI_HOST_ROW,
                "resourcePool": RESOURCE_POOL_ROW,
            },
        },
    )

    assert result.data == {"id": MOUNT_ID}
    assert _posted_body(httpx_mock, MOUNT_PATH) == {
        "restorePointId": RESTORE_POINT_ID,
        "type": "Customized",
        "secureRestore": {"antivirusScanEnabled": False, "yaraScanEnabled": False},
        "powerUp": False,
        "nicsEnabled": False,
        "overwrite": False,
        "destination": {
            "restoredVmName": "ydwin16vc-mcp-ir",
            "destinationHost": _ref(ESXI_HOST_ROW),
            "resourcePool": _ref(RESOURCE_POOL_ROW),
        },
        # VBR requires a datastore object for Customized; without a cache datastore redo logs stay in vPower NFS.
        "datastore": {"redirectEnabled": False},
    }


async def test_start_instant_recovery_sends_the_callers_overwrite_choice(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(url=f"{BASE}{MOUNT_PATH}", json={"id": MOUNT_ID})

    await mcp_client.call_tool(
        "start_instant_recovery_vsphere_vm", {"restore_point_id": RESTORE_POINT_ID, "overwrite": True}
    )

    assert _posted_body(httpx_mock, MOUNT_PATH)["overwrite"] is True


@pytest.mark.parametrize(
    ("destination", "datastore", "error"),
    [
        # VBR: "Host esx02.lab.local cannot be found in the configuration database".
        ({"destinationHost": ESXI_HA_HOST_ROW}, None, r"objectId 'ha-host', which VBR cannot resolve"),
        # VBR accepts the request but silently drops the folder.
        (
            {"destinationHost": ESXI_HOST_ROW, "folder": DATACENTER_ROW},
            None,
            "Datacenter row, which VBR silently ignores",
        ),
        ({"destinationHost": DATASTORE_ROW}, None, r"`destination.destinationHost` must be a Cluster or Host"),
        ({"destinationHost": ESXI_HOST_ROW, "resourcePool": DATASTORE_ROW}, None, "must be a ResourcePool"),
        (
            {"destinationHost": ESXI_HOST_ROW, "resourcePool": {**RESOURCE_POOL_ROW, "hostName": "vc01.lab.local"}},
            None,
            "belongs to managed server 'vc01.lab.local'",
        ),
        ({"destinationHost": ESXI_HOST_ROW}, {"cacheDatastore": DATASTORE_ROW}, "go together"),
        ({"destinationHost": ESXI_HOST_ROW}, {"redirectEnabled": True}, "go together"),
    ],
)
async def test_start_instant_recovery_rejects_bad_placement_before_calling_vbr(
    mcp_client: Client, destination: dict, datastore: dict | None, error: str
):
    arguments = {"restore_point_id": RESTORE_POINT_ID, "mode": "Customized", "destination": destination}
    if datastore is not None:
        arguments["datastore"] = datastore

    with pytest.raises(ToolError, match=error):
        await mcp_client.call_tool("start_instant_recovery_vsphere_vm", arguments)


async def test_start_instant_recovery_other_platform_sends_its_destination(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(url=f"{BASE}{MOUNT_PATH}", json={"id": MOUNT_ID})

    await mcp_client.call_tool(
        "start_instant_recovery_vsphere_vm",
        {
            "restore_point_id": RESTORE_POINT_ID,
            "mode": "OtherPlatform",
            "other_platform_destination": {
                "destinationHost": ESXI_HOST_ROW,
                "networkMapping": [{"sourceNetwork": SOURCE_NETWORK_INFO, "targetNetwork": NETWORK_ROW}],
            },
        },
    )

    body = _posted_body(httpx_mock, MOUNT_PATH)
    assert body["type"] == "OtherPlatform"
    assert body["destination"] == {
        "destinationHost": _ref(ESXI_HOST_ROW),
        "networkMapping": [{"sourceNetwork": SOURCE_NETWORK_INFO, "targetNetwork": _ref(NETWORK_ROW)}],
    }
    assert body["datastore"] == {"redirectEnabled": False}  # VBR requires one; redo logs stay in vPower NFS


@pytest.mark.parametrize(
    ("arguments", "error"),
    [
        ({"mode": "OtherPlatform"}, r'mode="OtherPlatform" requires: other_platform_destination'),
        (
            {
                "mode": "OtherPlatform",
                "other_platform_destination": {"destinationHost": ESXI_HOST_ROW},
                "destination": {},
            },
            r'mode="OtherPlatform" does not accept: destination',
        ),
        (
            {
                "mode": "OtherPlatform",
                "other_platform_destination": {"destinationHost": ESXI_HOST_ROW},
                "vm_tags_restore_enabled": True,
            },
            "does not accept: vm_tags_restore_enabled",
        ),
        (
            {
                "mode": "OtherPlatform",
                "other_platform_destination": {"destinationHost": ESXI_HOST_ROW, "folder": DATACENTER_ROW},
            },
            r"`other_platform_destination.folder` is a Datacenter row",
        ),
        (
            {
                "mode": "OtherPlatform",
                "other_platform_destination": {
                    "destinationHost": ESXI_HOST_ROW,
                    "networkMapping": [{"sourceNetwork": SOURCE_NETWORK_INFO, "targetNetwork": DATASTORE_ROW}],
                },
            },
            r"`other_platform_destination.networkMapping\[0\].targetNetwork` must be a DVSNetwork or Network",
        ),
        (
            {
                "mode": "OtherPlatform",
                "other_platform_destination": {
                    "destinationHost": ESXI_HOST_ROW,
                    "resourcePool": {**RESOURCE_POOL_ROW, "hostName": "vc01.lab.local"},
                },
            },
            "belongs to managed server 'vc01.lab.local'",
        ),
        (
            {
                "mode": "Customized",
                "destination": {"destinationHost": ESXI_HOST_ROW},
                "other_platform_destination": {"destinationHost": ESXI_HOST_ROW},
            },
            r'mode="Customized" does not accept: other_platform_destination',
        ),
        (
            {"other_platform_destination": {"destinationHost": ESXI_HOST_ROW}},
            r'mode="OriginalLocation" does not accept: other_platform_destination',
        ),
    ],
)
async def test_start_instant_recovery_checks_the_other_platform_destination(
    mcp_client: Client, arguments: dict, error: str
):
    with pytest.raises(ToolError, match=error):
        await mcp_client.call_tool(
            "start_instant_recovery_vsphere_vm", {"restore_point_id": RESTORE_POINT_ID, **arguments}
        )


def _add_restore_point_disks(httpx_mock: HTTPXMock, *names: str):
    httpx_mock.add_response(
        url=f"{BASE}/api/v1/restorePoints/{RESTORE_POINT_ID}/disks?skip=0&limit=200",
        json={"data": [{"name": name, "type": "Vi"} for name in names], "pagination": {"total": len(names)}},
    )


async def test_restore_vsphere_vm_customized_sends_the_lab_accepted_spec(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    _add_restore_point_disks(httpx_mock, "ydwin16vc")
    path = "/api/v1/restore/vmRestore/vSphere"
    httpx_mock.add_response(url=f"{BASE}{path}", json={"id": "session-7"})

    await mcp_client.call_tool(
        "restore_vsphere_vm",
        {
            "restore_point_id": RESTORE_POINT_ID,
            "mode": "Customized",
            "power_up": False,
            "restore_proxies": {"autoSelectEnabled": True},
            "destination_host": ESXI_HOST_ROW,
            "resource_pool": RESOURCE_POOL_ROW,
            "datastore": {
                "defaultDatastore": DATASTORE_ROW,
                "diskMappings": [{"diskName": "ydwin16vc", "datastore": DATASTORE_ROW, "diskType": "Thin"}],
            },
            "folder": {"folder": DATACENTER_ROW, "vmName": "ydwin16vc-mcp-restore", "restoreVmTags": True},
            "network": {
                "networks": [{"sourceNetwork": NETWORK_ROW, "targetNetwork": NETWORK_ROW}],
                "disconnected": True,
            },
        },
    )

    assert _posted_body(httpx_mock, path) == {
        "restorePointId": RESTORE_POINT_ID,
        "type": "Customized",
        "secureRestore": {"antivirusScanEnabled": False, "yaraScanEnabled": False},
        "powerUp": False,
        "overwrite": False,
        "restoreProxies": {"autoSelectEnabled": True},
        "destinationHost": _ref(ESXI_HOST_ROW),
        "resourcePool": _ref(RESOURCE_POOL_ROW),
        "datastore": {
            "defaultDatastore": _ref(DATASTORE_ROW),
            "diskMappings": [{"diskName": "ydwin16vc", "datastore": _ref(DATASTORE_ROW), "diskType": "Thin"}],
        },
        "folder": {"folder": _ref(DATACENTER_ROW), "vmName": "ydwin16vc-mcp-restore", "restoreVmTags": True},
        "network": {
            "networks": [{"sourceNetwork": _ref(NETWORK_ROW), "targetNetwork": _ref(NETWORK_ROW)}],
            "disconnected": True,
        },
    }


async def test_restore_vsphere_vm_rejects_a_disk_name_the_restore_point_does_not_have(
    mcp_client: Client, httpx_mock: HTTPXMock
):
    # VBR answers "Cannot find virtual disk with ID 'ydwin16vc.vmdk'" - it matches diskName against these names.
    _add_token_response(httpx_mock)
    _add_restore_point_disks(httpx_mock, "ydwin16vc")

    with pytest.raises(ToolError, match=r"Unknown .*'ydwin16vc\.vmdk'.*'ydwin16vc'"):
        await mcp_client.call_tool(
            "restore_vsphere_vm",
            {
                "restore_point_id": RESTORE_POINT_ID,
                "mode": "Customized",
                "destination_host": ESXI_HOST_ROW,
                "datastore": {
                    "defaultDatastore": DATASTORE_ROW,
                    "diskMappings": [{"diskName": "ydwin16vc.vmdk", "datastore": DATASTORE_ROW}],
                },
                "network": {"networks": [{"sourceNetwork": NETWORK_ROW, "targetNetwork": NETWORK_ROW}]},
            },
        )

    assert not any(r.url.path == "/api/v1/restore/vmRestore/vSphere" for r in httpx_mock.get_requests())


@pytest.mark.parametrize(
    ("arguments", "error"),
    [
        (
            {
                "destination_host": ESXI_HOST_ROW,
                "network": {"networks": [{"sourceNetwork": NETWORK_ROW, "targetNetwork": NETWORK_ROW}]},
            },
            "requires: datastore.defaultDatastore",
        ),
        (
            {
                "destination_host": ESXI_HA_HOST_ROW,
                "datastore": {"defaultDatastore": DATASTORE_ROW},
                "network": {"networks": [{"sourceNetwork": NETWORK_ROW, "targetNetwork": NETWORK_ROW}]},
            },
            "which VBR cannot resolve",
        ),
        (
            {
                "destination_host": ESXI_HOST_ROW,
                "datastore": {"defaultDatastore": DATASTORE_ROW},
                "network": {"networks": [{"sourceNetwork": NETWORK_ROW, "targetNetwork": DATASTORE_ROW}]},
            },
            r"targetNetwork` must be a DVSNetwork or Network",
        ),
        (
            {
                "destination_host": ESXI_HOST_ROW,
                "datastore": {"defaultDatastore": DATASTORE_ROW},
                "folder": {"folder": RESOURCE_POOL_ROW},
                "network": {"networks": [{"sourceNetwork": NETWORK_ROW, "targetNetwork": NETWORK_ROW}]},
            },
            r"`folder.folder` must be a Datacenter or Folder",
        ),
        (
            {
                "destination_host": ESXI_HOST_ROW,
                "datastore": {"defaultDatastore": DATASTORE_ROW},
                "network": {"networks": [{"sourceNetwork": NETWORK_ROW, "targetNetwork": NETWORK_ROW}]},
                "restore_proxies": {"autoSelectEnabled": False},
            },
            "needs `proxyIds`",
        ),
    ],
)
async def test_restore_vsphere_vm_customized_rejects_incomplete_or_wrong_placement(
    mcp_client: Client, arguments: dict, error: str
):
    with pytest.raises(ToolError, match=error):
        await mcp_client.call_tool(
            "restore_vsphere_vm", {"restore_point_id": RESTORE_POINT_ID, "mode": "Customized", **arguments}
        )


def _add_network_info(httpx_mock: HTTPXMock, *networks: dict):
    httpx_mock.add_response(
        url=f"{BASE}/api/v1/restorePoints/{RESTORE_POINT_ID}/networkInfo",
        json={"data": list(networks), "pagination": {"total": len(networks)}},
    )


async def test_restore_vsphere_vm_customized_without_network_is_rejected_for_a_vm_with_networks(
    mcp_client: Client, httpx_mock: HTTPXMock
):
    # VBR accepts the request and silently keeps the source network settings.
    _add_token_response(httpx_mock)
    _add_network_info(httpx_mock, SOURCE_NETWORK_INFO)

    with pytest.raises(ToolError, match=r"requires: network\. The VM was backed up with networks 'VM Network'"):
        await mcp_client.call_tool(
            "restore_vsphere_vm",
            {
                "restore_point_id": RESTORE_POINT_ID,
                "mode": "Customized",
                "destination_host": ESXI_HOST_ROW,
                "datastore": {"defaultDatastore": DATASTORE_ROW},
            },
        )

    assert not any(r.url.path == "/api/v1/restore/vmRestore/vSphere" for r in httpx_mock.get_requests())


async def test_restore_vsphere_vm_customized_without_network_restores_a_vm_without_networks(
    mcp_client: Client, httpx_mock: HTTPXMock
):
    _add_token_response(httpx_mock)
    _add_network_info(httpx_mock)
    path = "/api/v1/restore/vmRestore/vSphere"
    httpx_mock.add_response(url=f"{BASE}{path}", json={"id": "session-10"})

    await mcp_client.call_tool(
        "restore_vsphere_vm",
        {
            "restore_point_id": RESTORE_POINT_ID,
            "mode": "Customized",
            "destination_host": ESXI_HOST_ROW,
            "datastore": {"defaultDatastore": DATASTORE_ROW},
        },
    )

    assert "network" not in _posted_body(httpx_mock, path)


def _add_ir_vm_lookup(httpx_mock: HTTPXMock, disks: list[dict]):
    httpx_mock.add_response(
        url=f"{BASE}{MOUNT_PATH}/{MOUNT_ID}",
        json={
            "id": MOUNT_ID,
            "state": "Mounted",
            "vmName": "ydwin16vc-mcp-ir",
            "hostName": ESXI,
            "spec": {"destination": {"destinationHost": ESXI_HOST_ROW}},
        },
    )
    httpx_mock.add_response(
        url=f"{BASE}/api/v1/inventory/{ESXI}",
        json={
            "data": [
                {"type": "VirtualMachine", "hostName": ESXI, "name": "ydwin16vc-mcp-ir", "objectId": "243"},
            ],
            "pagination": {"total": 1},
        },
    )
    httpx_mock.add_response(url=f"{BASE}/api/v1/inventory/retrieveMachineDetails", json={"disks": disks})


async def test_migrate_fills_the_ir_vms_current_disk_name(mcp_client: Client, httpx_mock: HTTPXMock):
    # A failed migration left a snapshot behind, renaming the disk: the caller's id is enough, the name is read fresh.
    _add_token_response(httpx_mock)
    _add_ir_vm_lookup(httpx_mock, [{"id": 2000, "name": "ydwin16vc-000002.vmdk", "capacity": 48318382080.0}])
    httpx_mock.add_response(url=f"{BASE}{MOUNT_PATH}/{MOUNT_ID}/migrate", json={"id": "session-8"})

    await mcp_client.call_tool(
        "migrate_instant_recovery_vsphere_vm",
        {
            "mount_id": MOUNT_ID,
            "destination_host": ESXI_HOST_ROW,
            "resource_pool": RESOURCE_POOL_ROW,
            "datastore": {
                "defaultDatastore": DATASTORE_ROW,
                "diskMappings": [
                    {
                        "disk": {"id": 2000, "name": "ydwin16vc-000001.vmdk"},
                        "datastore": DATASTORE_ROW,
                        "diskType": "Thin",
                    }
                ],
            },
            "veeam_quick_migration_enabled": True,
            "delete_source_vm_files": False,
        },
    )

    assert _posted_body(httpx_mock, f"{MOUNT_PATH}/{MOUNT_ID}/migrate") == {
        "destinationHost": _ref(ESXI_HOST_ROW),
        "resourcePool": _ref(RESOURCE_POOL_ROW),
        "datastore": {
            "defaultDatastore": _ref(DATASTORE_ROW),
            "diskMappings": [
                {
                    "disk": {"id": 2000, "name": "ydwin16vc-000002.vmdk"},
                    "datastore": _ref(DATASTORE_ROW),
                    "diskType": "Thin",
                }
            ],
        },
        "VeeamQMEnabled": True,
        "DeleteSourceVmsFiles": False,
    }
    details = _posted_body(httpx_mock, "/api/v1/inventory/retrieveMachineDetails")
    assert details["object"]["objectId"] == "243"


async def test_migrate_rejects_a_disk_id_the_ir_vm_does_not_have(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    _add_ir_vm_lookup(httpx_mock, [{"id": 2000, "name": "ydwin16vc-000001.vmdk"}])

    with pytest.raises(ToolError, match=r"no disk with id 2001; its disks are: 2000 \(ydwin16vc-000001\.vmdk\)"):
        await mcp_client.call_tool(
            "migrate_instant_recovery_vsphere_vm",
            {
                "mount_id": MOUNT_ID,
                "destination_host": ESXI_HOST_ROW,
                "datastore": {"diskMappings": [{"disk": {"id": 2001}, "datastore": DATASTORE_ROW}]},
            },
        )

    assert not any(r.url.path.endswith("/migrate") for r in httpx_mock.get_requests())


def _add_same_named_vms(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{BASE}{MOUNT_PATH}/{MOUNT_ID}",
        json={"id": MOUNT_ID, "state": "Mounted", "vmName": "ydwin16vc", "hostName": ESXI},
    )
    rows = [
        {"type": "VirtualMachine", "hostName": ESXI, "name": "ydwin16vc", "objectId": object_id}
        for object_id in ("12", "243")  # the original, still registered, and the Instant Recovery VM
    ]
    httpx_mock.add_response(url=f"{BASE}/api/v1/inventory/{ESXI}", json={"data": rows, "pagination": {"total": 2}})


async def test_migrate_does_not_guess_between_same_named_vms(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    _add_same_named_vms(httpx_mock)

    with pytest.raises(ToolError, match=r"2 VMs in the inventory are named 'ydwin16vc'.*disk\.name` yourself"):
        await mcp_client.call_tool(
            "migrate_instant_recovery_vsphere_vm",
            {
                "mount_id": MOUNT_ID,
                "destination_host": ESXI_HOST_ROW,
                "datastore": {"diskMappings": [{"disk": {"id": 2000}, "datastore": DATASTORE_ROW}]},
            },
        )

    requests = httpx_mock.get_requests()
    assert not any(r.url.path.endswith(("/retrieveMachineDetails", "/migrate")) for r in requests)


async def test_migrate_sends_the_callers_disk_names_when_the_vm_is_ambiguous(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    _add_same_named_vms(httpx_mock)
    httpx_mock.add_response(url=f"{BASE}{MOUNT_PATH}/{MOUNT_ID}/migrate", json={"id": "session-11"})
    disk = {"id": 2000, "name": "ydwin16vc-000001.vmdk"}

    await mcp_client.call_tool(
        "migrate_instant_recovery_vsphere_vm",
        {
            "mount_id": MOUNT_ID,
            "destination_host": ESXI_HOST_ROW,
            "datastore": {"diskMappings": [{"disk": disk, "datastore": DATASTORE_ROW}]},
        },
    )

    assert _posted_body(httpx_mock, f"{MOUNT_PATH}/{MOUNT_ID}/migrate")["datastore"]["diskMappings"][0]["disk"] == disk


async def test_migrate_rejects_a_resource_pool_from_another_server(mcp_client: Client):
    with pytest.raises(ToolError, match="belongs to managed server 'other-vc'"):
        await mcp_client.call_tool(
            "migrate_instant_recovery_vsphere_vm",
            {
                "mount_id": MOUNT_ID,
                "destination_host": ESXI_HOST_ROW,
                "resource_pool": {**RESOURCE_POOL_ROW, "hostName": "other-vc"},
            },
        )


async def test_restore_object_storage_refuses_overwrite_options_for_a_new_bucket(mcp_client: Client):
    with pytest.raises(ToolError, match="do not apply to a new bucket"):
        await mcp_client.call_tool(
            "restore_object_storage",
            {
                "restore_point_id": RESTORE_POINT_ID,
                "destination": {"newBucketName": "restored"},
                "restore_options": {"overwriteMode": "Overwrite"},
            },
        )


async def test_restore_file_share_defaults_the_target_path_to_the_share_root(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    server_id = "6a7b3f1e-2c3d-4e5f-8a9b-0c1d2e3f4a5b"
    httpx_mock.add_response(
        url=f"{BASE}/api/v1/inventory/unstructuredDataServers/{server_id}",
        json={"id": server_id, "path": "\\\\nas02\\share"},
    )
    path = "/api/v1/restore/unstructuredData/fileShare"
    httpx_mock.add_response(url=f"{BASE}{path}", json={"id": "session-9"})

    await mcp_client.call_tool(
        "restore_file_share",
        {"restore_point_id": RESTORE_POINT_ID, "destination": {"unstructuredDataServerId": server_id}},
    )

    assert _posted_body(httpx_mock, path)["destination"] == {
        "unstructuredDataServerId": server_id,
        "path": "\\\\nas02\\share",
    }
