/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { FetchPolicyRegistry } from '../types';

// Ported from veeam-intelligence frontend/agents/src/fetchPolicies/vbr_13.1.ts (identical for VBR 13.2).
// Keep in sync with the product's REST API Permission Matrix for the "Advanced With Actions Chat Bot" role.

/**
 * Shared fetch policy for VBR 13.1 (REST API v1).
 *
 * Single source of truth for both VBR 13.1 hosts — the web plugin (`vbr_13.1`) and the
 * WPF console (`vbr_console_13.1`) — so state-changing VBR REST endpoints are gated
 * identically across both. Add new VBR 13.1 endpoints here once.
 *
 * Coverage target: every non-GET endpoint the "Advanced With Actions Chat Bot" role may call
 * (per the REST API Permission Matrix — VBR 13.1, AccessModel 1.0.82). The gate REJECTS any
 * non-GET request that matches neither list, so an endpoint the role is allowed to invoke must
 * appear here or it is blocked at runtime. GET requests are read-only and pre-approved by the
 * gate, so only non-GET endpoints appear here.
 *
 *   - `whitelist` — state-changing endpoints the assistant may invoke silently. These are
 *     read/discovery (POST queries), validation/`check*`/`resolve*Defaults`, or routine-maintenance
 *     calls with no destructive side effects, so they carry empty title/description keys (the
 *     confirmation prompt is never shown).
 *   - `checklist` — state-changing endpoints that require explicit user confirmation. Each
 *     entry's `titleKey` / `descriptionKey` references a string in the `fetchPolicy`
 *     localization namespace, which each host resolves against its own bundle
 *     (web: `localization/vbr_13.1/fetchPolicy`; console: `localization/vbr_console_13.1`).
 *     Both namespaces must keep all referenced keys present.
 *
 * Path patterns use `:param` placeholders for path variables (matched segment-by-segment).
 */
export const vbr_13_1_FetchPolicies: FetchPolicyRegistry = {
    whitelist: [
        // --- Public REST API ---

        // Read-only — returns the access control list for an object (POST carries the query body).
        {
            method: 'POST',
            pathPattern: '/api/v1/acl',
            titleKey: '',
            descriptionKey: '',
        },
        // Read/discovery — lists restore points for an unstructured-data FLR session.
        {
            method: 'POST',
            pathPattern: '/api/v1/backupbrowser/flr/unstructuredData/:sessionId/restorePoints',
            titleKey: '',
            descriptionKey: '',
        },
        // Routine maintenance — rescans all managed servers to refresh discovered objects.
        {
            method: 'POST',
            pathPattern: '/api/v1/backupInfrastructure/managedServers/rescan',
            titleKey: '',
            descriptionKey: '',
        },
        // Read/discovery — rescans a managed server to refresh discovered objects.
        {
            method: 'POST',
            pathPattern: '/api/v1/backupInfrastructure/managedServers/:id/rescan',
            titleKey: '',
            descriptionKey: '',
        },
        // Routine maintenance — resyncs repository metadata with storage, no destructive side effects.
        {
            method: 'POST',
            pathPattern: '/api/v1/backupInfrastructure/repositories/rescan',
            titleKey: '',
            descriptionKey: '',
        },
        // Read-only — returns detailed backup information (POST carries the query body).
        {
            method: 'POST',
            pathPattern: '/api/v1/backups/:id/details',
            titleKey: '',
            descriptionKey: '',
        },
        // Routine maintenance — snapshots the VBR configuration, no destructive side effects.
        {
            method: 'POST',
            pathPattern: '/api/v1/configBackup/backup',
            titleKey: '',
            descriptionKey: '',
        },
        // Read/collect — exports support logs.
        {
            method: 'POST',
            pathPattern: '/api/v1/exportlogs',
            titleKey: '',
            descriptionKey: '',
        },
        // Read/discovery — enumerates all inventory hosts.
        {
            method: 'POST',
            pathPattern: '/api/v1/inventory',
            titleKey: '',
            descriptionKey: '',
        },
        // Read/discovery — inventory objects for a hostname.
        {
            method: 'POST',
            pathPattern: '/api/v1/inventory/:hostname',
            titleKey: '',
            descriptionKey: '',
        },
        // Read/discovery — enumerates physical protection groups.
        {
            method: 'POST',
            pathPattern: '/api/v1/inventory/physical',
            titleKey: '',
            descriptionKey: '',
        },
        // Read/discovery — inventory for a specific protection group.
        {
            method: 'POST',
            pathPattern: '/api/v1/inventory/physical/:protectionGroupId',
            titleKey: '',
            descriptionKey: '',
        },
        // Read/discovery — inventory for all physical protection groups.
        {
            method: 'POST',
            pathPattern: '/api/v1/inventory/physical/all',
            titleKey: '',
            descriptionKey: '',
        },
        // Read/discovery — returns machine detail info.
        {
            method: 'POST',
            pathPattern: '/api/v1/inventory/retrieveMachineDetails',
            titleKey: '',
            descriptionKey: '',
        },
        // Read/discovery — starts browsing an unstructured-data server (enumeration only).
        {
            method: 'POST',
            pathPattern: '/api/v1/inventory/unstructuredDataServers/:id/startBrowse',
            titleKey: '',
            descriptionKey: '',
        },
        // Read/discovery — browses an unstructured-data server session.
        {
            method: 'POST',
            pathPattern: '/api/v1/inventory/unstructuredDataServers/sessions/:id/browse',
            titleKey: '',
            descriptionKey: '',
        },
        // Read/discovery — stops an unstructured-data browse session (enumeration teardown).
        {
            method: 'POST',
            pathPattern: '/api/v1/inventory/unstructuredDataServers/sessions/:id/stop',
            titleKey: '',
            descriptionKey: '',
        },
        // Read-only — generates a license usage report.
        {
            method: 'POST',
            pathPattern: '/api/v1/license/createReport',
            titleKey: '',
            descriptionKey: '',
        },
        // Read-only — returns network info for a restore point (POST carries the query body).
        {
            method: 'POST',
            pathPattern: '/api/v1/restorePoints/:id/networkInfo',
            titleKey: '',
            descriptionKey: '',
        },

        // --- Private REST API ---

        // Login — exchanges the host token for a VBR extension session.
        {
            method: 'POST',
            pathPattern: '/private-api/oauth2/vbr_extension',
            titleKey: '',
            descriptionKey: '',
        },
        // Read/prepare — prepares data for a remote BMR job session (no execution).
        {
            method: 'POST',
            pathPattern: '/private-api/v1/agents/recoveryAppliances/forPrepareForRemoteBmrJobSession',
            titleKey: '',
            descriptionKey: '',
        },
        // Read/discovery — backup browser tree (children).
        {
            method: 'POST',
            pathPattern: '/private-api/v1/backupBrowser/children',
            titleKey: '',
            descriptionKey: '',
        },
        // Read/discovery — backup browser item details.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/backupBrowser/details',
            titleKey: '',
            descriptionKey: '',
        },
        // Read/discovery — initializes a backup browser session.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/backupBrowser/init',
            titleKey: '',
            descriptionKey: '',
        },
        // Read/discovery — backup browser roots.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/backupBrowser/roots',
            titleKey: '',
            descriptionKey: '',
        },
        // Read-only — managed server states (POST carries the query body).
        {
            method: 'POST',
            pathPattern: '/private-api/v1/backupInfrastructure/managedServers/states',
            titleKey: '',
            descriptionKey: '',
        },
        // Read-only — proxy states (POST carries the query body).
        {
            method: 'POST',
            pathPattern: '/private-api/v1/backupInfrastructure/proxies/states',
            titleKey: '',
            descriptionKey: '',
        },
        // Read/discovery — resolves available repository gateways.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/backupInfrastructure/repositories/gateways/getAvailable',
            titleKey: '',
            descriptionKey: '',
        },
        // Read-only — backup objects (POST carries the query body).
        {
            method: 'POST',
            pathPattern: '/private-api/v1/backups/objects',
            titleKey: '',
            descriptionKey: '',
        },
        // Routine — assistant client component auto-update (trigger, no customer-data side effects).
        {
            method: 'POST',
            pathPattern: '/private-api/v1/client/autoupdate',
            titleKey: '',
            descriptionKey: '',
        },
        // Read/download — assistant client component package.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/client/autoupdate/download',
            titleKey: '',
            descriptionKey: '',
        },
        // Read-only — assistant client component update metadata.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/client/autoupdate/metadata',
            titleKey: '',
            descriptionKey: '',
        },
        // Read-only — endpoint host backup jobs view model (POST carries the query body).
        {
            method: 'POST',
            pathPattern: '/private-api/v1/inventory/viewModel/epHosts/backupJobs',
            titleKey: '',
            descriptionKey: '',
        },
        // Read-only — endpoint host protection groups view model (POST carries the query body).
        {
            method: 'POST',
            pathPattern: '/private-api/v1/inventory/viewModel/epHosts/protectionGroups',
            titleKey: '',
            descriptionKey: '',
        },
        // Read-only — protection groups backup jobs view model (POST carries the query body).
        {
            method: 'POST',
            pathPattern: '/private-api/v1/inventory/viewModel/protectionGroups/backupJobs',
            titleKey: '',
            descriptionKey: '',
        },
        // Read-only — returns a job sample/preview.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/jobs/sample',
            titleKey: '',
            descriptionKey: '',
        },
        // Read-only — job states (POST carries the query body).
        {
            method: 'POST',
            pathPattern: '/private-api/v1/jobs/states',
            titleKey: '',
            descriptionKey: '',
        },
        // Read-only — job states scoped to inventory (POST carries the query body).
        {
            method: 'POST',
            pathPattern: '/private-api/v1/jobs/states/withInventoryScope',
            titleKey: '',
            descriptionKey: '',
        },
        // Read/prepare — resolves an unstructured-backup file object (no execution).
        {
            method: 'POST',
            pathPattern: '/private-api/v1/jobs/unstructuredBackup/object/prepareFileBackupObject',
            titleKey: '',
            descriptionKey: '',
        },
        // Read/prepare — resolves an unstructured-backup object (no execution).
        {
            method: 'POST',
            pathPattern: '/private-api/v1/jobs/unstructuredBackup/object/prepareObject',
            titleKey: '',
            descriptionKey: '',
        },
        // Read/prepare — resolves an unstructured-backup object-storage object (no execution).
        {
            method: 'POST',
            pathPattern: '/private-api/v1/jobs/unstructuredBackup/object/prepareObjectStorageBackupObject',
            titleKey: '',
            descriptionKey: '',
        },
        // Validation — checks job object ACLs.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/jobs/validation/checkJobObjectsAcl',
            titleKey: '',
            descriptionKey: '',
        },
        // Validation — checks a job name.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/jobs/validation/name',
            titleKey: '',
            descriptionKey: '',
        },
        // Validation — pre-flight check before starting a job.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/jobs/validation/validateStartJob',
            titleKey: '',
            descriptionKey: '',
        },
        // Validation — pre-flight check before stopping a job.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/jobs/validation/validateStopJob',
            titleKey: '',
            descriptionKey: '',
        },
        // Validation — checks a license before install.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/license/validation/install',
            titleKey: '',
            descriptionKey: '',
        },
        // Validation — checks a license instance assignment.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/license/validation/instances/assign',
            titleKey: '',
            descriptionKey: '',
        },
        // Routine maintenance — rescans mount server components.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/mountserver/components/rescan',
            titleKey: '',
            descriptionKey: '',
        },
        // Read/discovery — lists mount server candidates.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/mountservers/candidates',
            titleKey: '',
            descriptionKey: '',
        },
        // Read-only — returns effective permissions for the given objects (POST carries the query body).
        {
            method: 'POST',
            pathPattern: '/private-api/v1/permissions',
            titleKey: '',
            descriptionKey: '',
        },
        // Routine — keep-alive heartbeat for a platform plugin job session (no side effects).
        {
            method: 'POST',
            pathPattern: '/private-api/v1/platform/plugins/job/sessions/:tag/keepAlive',
            titleKey: '',
            descriptionKey: '',
        },
        // Read/prepare — prepares a VM replication task (no execution).
        {
            method: 'POST',
            pathPattern: '/private-api/v1/platform/plugins/job/sessions/:tag/prepareVmReplicationTask',
            titleKey: '',
            descriptionKey: '',
        },
        // Read/discovery — finds all replicas.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/platform/plugins/replicas/find/all/replicas',
            titleKey: '',
            descriptionKey: '',
        },
        // Read/discovery — finds a replica.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/platform/plugins/replicas/find/replica',
            titleKey: '',
            descriptionKey: '',
        },
        // Validation — checks an endpoint host operation for a protection group.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/protectionGroups/validation/checkEpHostOperation',
            titleKey: '',
            descriptionKey: '',
        },
        // Validation — checks a server added as a file proxy.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/proxies/validation/CheckAddedServerForFileProxy',
            titleKey: '',
            descriptionKey: '',
        },
        // Validation — checks a file proxy server.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/proxies/validation/CheckFileProxyServer',
            titleKey: '',
            descriptionKey: '',
        },
        // Validation — checks the last-proxy-disable request.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/proxies/validation/RequestLastProxyDisable',
            titleKey: '',
            descriptionKey: '',
        },
        // Validation — checks a Hyper-V proxy server.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/proxies/validation/:hostId/checkHvProxyServer',
            titleKey: '',
            descriptionKey: '',
        },
        // Validation — checks a vSphere Linux proxy server.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/proxies/validation/:hostId/checkViProxyLinuxServer',
            titleKey: '',
            descriptionKey: '',
        },
        // Validation — checks a vSphere Windows proxy server.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/proxies/validation/:hostId/checkViProxyWindowsServer',
            titleKey: '',
            descriptionKey: '',
        },
        // Read/discovery — discovers proxy packages on a host.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/proxies/validation/:hostId/discoverPackages',
            titleKey: '',
            descriptionKey: '',
        },
        // Read-only — computes the max task count for a proxy host.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/proxies/validation/:hostId/maxTasksCount',
            titleKey: '',
            descriptionKey: '',
        },
        // Validation — checks the target host filesystem path for restore.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/restore/checkTargetHostFsPath',
            titleKey: '',
            descriptionKey: '',
        },
        // Validation — vSphere Instant Recovery datastore check.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/restore/instantRecovery/vSphere/checkVmwareInstantRecoveryDatastore',
            titleKey: '',
            descriptionKey: '',
        },
        // Validation — vSphere Instant Recovery folder check.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/restore/instantRecovery/vSphere/checkVmwareInstantRecoveryFolder',
            titleKey: '',
            descriptionKey: '',
        },
        // Validation — vSphere Instant Recovery helper appliance check.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/restore/instantRecovery/vSphere/checkVmwareInstantRecoveryHelperAppliance',
            titleKey: '',
            descriptionKey: '',
        },
        // Validation — vSphere Instant Recovery host check.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/restore/instantRecovery/vSphere/checkVmwareInstantRecoveryHost',
            titleKey: '',
            descriptionKey: '',
        },
        // Validation — vSphere Instant Recovery mode check.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/restore/instantRecovery/vSphere/checkVmwareInstantRecoveryMode',
            titleKey: '',
            descriptionKey: '',
        },
        // Validation — vSphere Instant Recovery source items check.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/restore/instantRecovery/vSphere/checkVmwareInstantRecoverySourceItems',
            titleKey: '',
            descriptionKey: '',
        },
        // Validation — vSphere Instant Recovery spec check.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/restore/instantRecovery/vSphere/checkVmwareInstantRecoverySpec',
            titleKey: '',
            descriptionKey: '',
        },
        // Read/resolve — batch defaults for vSphere Instant Recovery.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/restore/instantRecovery/vSphere/resolveBatchDefaults',
            titleKey: '',
            descriptionKey: '',
        },
        // Read/resolve — defaults for a vSphere Instant Recovery VM migration.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/restore/instantRecovery/vSphere/vm/migrate/defaults',
            titleKey: '',
            descriptionKey: '',
        },
        // Validation — Hyper-V entire VM restore datastore check.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/restore/validation/checkHyperVEntireVmRestoreDatastore',
            titleKey: '',
            descriptionKey: '',
        },
        // Validation — Hyper-V entire VM restore host check.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/restore/validation/checkHyperVEntireVmRestoreHost',
            titleKey: '',
            descriptionKey: '',
        },
        // Validation — Hyper-V entire VM restore mode check.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/restore/validation/checkHyperVEntireVmRestoreMode',
            titleKey: '',
            descriptionKey: '',
        },
        // Validation — Hyper-V entire VM restore name check.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/restore/validation/checkHyperVEntireVmRestoreName',
            titleKey: '',
            descriptionKey: '',
        },
        // Validation — Hyper-V entire VM restore source items check.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/restore/validation/checkHyperVEntireVmRestoreSourceItems',
            titleKey: '',
            descriptionKey: '',
        },
        // Validation — Hyper-V entire VM restore VMs check.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/restore/validation/checkHyperVEntireVmRestoreVms',
            titleKey: '',
            descriptionKey: '',
        },
        // Validation — NAS restore destination check.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/restore/validation/checkNasRestoreDestination',
            titleKey: '',
            descriptionKey: '',
        },
        // Validation — NAS restore file share options check.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/restore/validation/checkNasRestoreFileShareOptions',
            titleKey: '',
            descriptionKey: '',
        },
        // Validation — NAS restore object storage new bucket check.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/restore/validation/checkNasRestoreObjectStorageNewBucket',
            titleKey: '',
            descriptionKey: '',
        },
        // Validation — NAS restore object storage options check.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/restore/validation/checkNasRestoreObjectStorageOptions',
            titleKey: '',
            descriptionKey: '',
        },
        // Validation — restore reason check.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/restore/validation/checkRestoreReason',
            titleKey: '',
            descriptionKey: '',
        },
        // Validation — secure restore spec check.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/restore/validation/checkSecureRestoreSpec',
            titleKey: '',
            descriptionKey: '',
        },
        // Validation — vSphere entire VM restore datastore check.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/restore/validation/checkVmwareEntireVmRestoreDatastore',
            titleKey: '',
            descriptionKey: '',
        },
        // Validation — vSphere entire VM restore folder check.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/restore/validation/checkVmwareEntireVmRestoreFolder',
            titleKey: '',
            descriptionKey: '',
        },
        // Validation — vSphere entire VM restore host check.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/restore/validation/checkVmwareEntireVmRestoreHost',
            titleKey: '',
            descriptionKey: '',
        },
        // Validation — vSphere entire VM restore mode check.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/restore/validation/checkVmwareEntireVmRestoreMode',
            titleKey: '',
            descriptionKey: '',
        },
        // Validation — vSphere entire VM restore source items check.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/restore/validation/checkVmwareEntireVmRestoreSourceItems',
            titleKey: '',
            descriptionKey: '',
        },
        // Validation — vSphere entire VM restore spec check.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/restore/validation/checkVmwareEntireVmRestoreSpec',
            titleKey: '',
            descriptionKey: '',
        },
        // Validation — vSphere quick migration destination check.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/restore/validation/checkVmwareQuickMigrationDestination',
            titleKey: '',
            descriptionKey: '',
        },
        // Validation — vSphere quick migration options check.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/restore/validation/checkVmwareQuickMigrationOptions',
            titleKey: '',
            descriptionKey: '',
        },
        // Validation — vSphere quick migration source items check.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/restore/validation/checkVmwareQuickMigrationSourceItems',
            titleKey: '',
            descriptionKey: '',
        },
        // Read/resolve — defaults for a Hyper-V entire VM restore.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/restore/vmRestore/hyperV/resolveDefaults',
            titleKey: '',
            descriptionKey: '',
        },
        // Read/resolve — batch defaults for a vSphere entire VM restore.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/restore/vmRestore/vSphere/resolveBatchDefaults',
            titleKey: '',
            descriptionKey: '',
        },
        // Read/resolve — defaults for a vSphere entire VM restore.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/restore/vmRestore/vSphere/resolveDefaults',
            titleKey: '',
            descriptionKey: '',
        },
        // Read/discovery — available archive-tier repositories for a scale-out repository.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/scale/out/backup/repository/archive/tier/available/repositories',
            titleKey: '',
            descriptionKey: '',
        },
        // Read-only — checks for available product updates.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/vbrinfo/check_updates',
            titleKey: '',
            descriptionKey: '',
        },
        // Login — authenticates the Veeam Intelligence service.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/veeamintelligence/authenticate',
            titleKey: '',
            descriptionKey: '',
        },
        // Read/collect — submits Veeam Intelligence logs.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/veeamintelligence/logs',
            titleKey: '',
            descriptionKey: '',
        },
        // Read-only — Veeam Intelligence service info (POST carries the query body).
        {
            method: 'POST',
            pathPattern: '/private-api/v1/veeamintelligence/serviceInfo',
            titleKey: '',
            descriptionKey: '',
        },
        // NOTE: PUT endpoints (e.g. PUT /private-api/v1/ui/settings, PUT
        // /api/v1/backupInfrastructure/proxies/:id) are intentionally omitted — the host fetch
        // transport / gate only models GET and POST (see HostFetchMethod), so PUT requests cannot
        // flow through this gate and need no policy entry here.
    ],
    checklist: [
        // --- Managed servers ---
        // Restarts transport/data-mover services on the targeted hosts and fails any
        // in-flight tasks running on them, so it is confirmation-gated rather than silent.
        {
            method: 'POST',
            pathPattern: '/api/v1/backupInfrastructure/managedServers/updateComponents',
            titleKey: 'update_managed_server_components_title',
            descriptionKey: 'update_managed_server_components_description',
        },
        // --- Backup proxies ---
        {
            method: 'POST',
            pathPattern: '/api/v1/backupInfrastructure/proxies/:id/enable',
            titleKey: 'enable_proxy_title',
            descriptionKey: 'enable_proxy_description',
        },
        {
            method: 'POST',
            pathPattern: '/api/v1/backupInfrastructure/proxies/:id/disable',
            titleKey: 'disable_proxy_title',
            descriptionKey: 'disable_proxy_description',
        },
        // --- Scale-out backup repositories ---
        {
            method: 'POST',
            pathPattern: '/api/v1/backupInfrastructure/scaleOutRepositories/:id/enableMaintenanceMode',
            titleKey: 'enable_repository_maintenance_mode_title',
            descriptionKey: 'enable_repository_maintenance_mode_description',
        },
        {
            method: 'POST',
            pathPattern: '/api/v1/backupInfrastructure/scaleOutRepositories/:id/disableMaintenanceMode',
            titleKey: 'disable_repository_maintenance_mode_title',
            descriptionKey: 'disable_repository_maintenance_mode_description',
        },
        {
            method: 'POST',
            pathPattern: '/api/v1/backupInfrastructure/scaleOutRepositories/:id/enableSealedMode',
            titleKey: 'enable_repository_sealed_mode_title',
            descriptionKey: 'enable_repository_sealed_mode_description',
        },
        {
            method: 'POST',
            pathPattern: '/api/v1/backupInfrastructure/scaleOutRepositories/:id/disableSealedMode',
            titleKey: 'disable_repository_sealed_mode_title',
            descriptionKey: 'disable_repository_sealed_mode_description',
        },
        // --- Jobs ---
        {
            method: 'POST',
            pathPattern: '/api/v1/jobs/:id/enable',
            titleKey: 'enable_job_title',
            descriptionKey: 'enable_job_description',
        },
        {
            method: 'POST',
            pathPattern: '/api/v1/jobs/:id/disable',
            titleKey: 'disable_job_title',
            descriptionKey: 'disable_job_description',
        },
        {
            method: 'POST',
            pathPattern: '/api/v1/jobs/:id/start',
            titleKey: 'start_job_title',
            descriptionKey: 'start_job_description',
        },
        {
            method: 'POST',
            pathPattern: '/api/v1/jobs/:id/stop',
            titleKey: 'stop_job_title',
            descriptionKey: 'stop_job_description',
        },
        {
            method: 'POST',
            pathPattern: '/api/v1/jobs/:id/retry',
            titleKey: 'retry_job_title',
            descriptionKey: 'retry_job_description',
        },
        // --- License ---
        {
            method: 'POST',
            pathPattern: '/api/v1/license/install',
            titleKey: 'install_license_title',
            descriptionKey: 'install_license_description',
        },
        {
            method: 'POST',
            pathPattern: '/api/v1/license/update',
            titleKey: 'update_license_title',
            descriptionKey: 'update_license_description',
        },
        {
            method: 'POST',
            pathPattern: '/api/v1/license/autoupdate',
            titleKey: 'set_license_autoupdate_title',
            descriptionKey: 'set_license_autoupdate_description',
        },
        {
            method: 'POST',
            pathPattern: '/api/v1/license/agentConsumption',
            titleKey: 'set_unlicensed_agent_consumption_title',
            descriptionKey: 'set_unlicensed_agent_consumption_description',
        },
        {
            method: 'POST',
            pathPattern: '/api/v1/license/capacity/:instanceId/revoke',
            titleKey: 'revoke_capacity_license_title',
            descriptionKey: 'revoke_capacity_license_description',
        },
        {
            method: 'POST',
            pathPattern: '/api/v1/license/instances/:instanceId/revoke',
            titleKey: 'revoke_instance_license_title',
            descriptionKey: 'revoke_instance_license_description',
        },
        {
            method: 'POST',
            pathPattern: '/api/v1/license/instances/:instanceId/remove',
            titleKey: 'remove_instance_license_title',
            descriptionKey: 'remove_instance_license_description',
        },
        {
            method: 'POST',
            pathPattern: '/api/v1/license/sockets/:hostId/revoke',
            titleKey: 'revoke_socket_license_title',
            descriptionKey: 'revoke_socket_license_description',
        },
        {
            method: 'POST',
            pathPattern: '/private-api/v1/license/installDatacenter',
            titleKey: 'install_datacenter_license_title',
            descriptionKey: 'install_datacenter_license_description',
        },
        // --- Malware detection ---
        {
            method: 'POST',
            pathPattern: '/api/v1/malwareDetection/scanBackup',
            titleKey: 'scan_backup_title',
            descriptionKey: 'scan_backup_description',
        },
        {
            method: 'POST',
            pathPattern: '/api/v1/malwareDetection/analyzeEncryption',
            titleKey: 'analyze_encryption_title',
            descriptionKey: 'analyze_encryption_description',
        },
        // --- Instant Recovery / restore (public) ---
        {
            method: 'POST',
            pathPattern: '/api/v1/restore/instantRecovery/vSphere/vm',
            titleKey: 'start_instant_recovery_vm_title',
            descriptionKey: 'start_instant_recovery_vm_description',
        },
        {
            method: 'POST',
            pathPattern: '/api/v1/restore/instantRecovery/vSphere/vm/:mountId/migrate',
            titleKey: 'migrate_instant_recovery_vm_title',
            descriptionKey: 'migrate_instant_recovery_vm_description',
        },
        {
            method: 'POST',
            pathPattern: '/api/v1/restore/instantRecovery/vSphere/vm/:mountId/unmount',
            titleKey: 'unmount_instant_recovery_vm_title',
            descriptionKey: 'unmount_instant_recovery_vm_description',
        },
        {
            method: 'POST',
            pathPattern: '/api/v1/restore/instantRecovery/hyperV/vm/:mountId/migrate',
            titleKey: 'migrate_instant_recovery_hyperv_vm_title',
            descriptionKey: 'migrate_instant_recovery_hyperv_vm_description',
        },
        {
            method: 'POST',
            pathPattern: '/api/v1/restore/instantRecovery/hyperV/vm/:mountId/unmount',
            titleKey: 'unmount_instant_recovery_hyperv_vm_title',
            descriptionKey: 'unmount_instant_recovery_hyperv_vm_description',
        },
        {
            method: 'POST',
            pathPattern: '/api/v1/restore/unstructuredData/fileShare',
            titleKey: 'restore_file_share_title',
            descriptionKey: 'restore_file_share_description',
        },
        {
            method: 'POST',
            pathPattern: '/api/v1/restore/unstructuredData/objectStorage',
            titleKey: 'restore_object_storage_title',
            descriptionKey: 'restore_object_storage_description',
        },
        {
            method: 'POST',
            pathPattern: '/api/v1/restore/vmRestore/vSphere',
            titleKey: 'restore_vm_title',
            descriptionKey: 'restore_vm_description',
        },
        {
            method: 'POST',
            pathPattern: '/api/v1/restore/vmRestore/hyperV',
            titleKey: 'restore_hyperv_vm_title',
            descriptionKey: 'restore_hyperv_vm_description',
        },
        // --- Instant Recovery / restore (private) ---
        {
            method: 'POST',
            pathPattern: '/private-api/v1/restore/adForest/start',
            titleKey: 'restore_ad_forest_title',
            descriptionKey: 'restore_ad_forest_description',
        },
        {
            method: 'POST',
            pathPattern: '/private-api/v1/restore/instantRecovery/sessions',
            titleKey: 'start_instant_recovery_session_title',
            descriptionKey: 'start_instant_recovery_session_description',
        },
        {
            method: 'POST',
            pathPattern: '/private-api/v1/restore/instantRecovery/vSphere/vm/migrate',
            titleKey: 'migrate_instant_recovery_vm_title',
            descriptionKey: 'migrate_instant_recovery_vm_description',
        },
        // --- Agents ---
        {
            method: 'POST',
            pathPattern: '/private-api/v1/agents/discoveredEntities/upgradeAgent',
            titleKey: 'upgrade_agent_title',
            descriptionKey: 'upgrade_agent_description',
        },
        // --- Product updates ---
        {
            method: 'POST',
            pathPattern: '/private-api/v1/vbrinfo/install_updates',
            titleKey: 'install_product_updates_title',
            descriptionKey: 'install_product_updates_description',
        },
        // --- Log export ---
        // Collects support logs for the selected job and uploads them to the Veeam Intelligence
        // backend for deep log analysis — gated because it packages and transfers diagnostic data.
        {
            method: 'POST',
            pathPattern: '/private-api/v1/veeamIntelligence/logExport/collectJobLogs',
            titleKey: 'collect_job_logs_title',
            descriptionKey: 'collect_job_logs_description',
        },
        // --- Platform plugin replication job sessions ---
        {
            method: 'POST',
            pathPattern: '/private-api/v1/platform/plugins/job/sessions/:tag/start',
            titleKey: 'start_replication_session_title',
            descriptionKey: 'start_replication_session_description',
        },
        {
            method: 'POST',
            pathPattern: '/private-api/v1/platform/plugins/job/sessions/:tag/stop',
            titleKey: 'stop_replication_session_title',
            descriptionKey: 'stop_replication_session_description',
        },
        {
            method: 'POST',
            pathPattern: '/private-api/v1/platform/plugins/job/sessions/:tag/cancelVmReplicationTask',
            titleKey: 'cancel_vm_replication_task_title',
            descriptionKey: 'cancel_vm_replication_task_description',
        },
        {
            method: 'POST',
            pathPattern: '/private-api/v1/platform/plugins/job/sessions/:tag/startVmReplicationTask',
            titleKey: 'start_vm_replication_task_title',
            descriptionKey: 'start_vm_replication_task_description',
        },
        // --- Platform plugin replica failover / failback ---
        {
            method: 'POST',
            pathPattern: '/private-api/v1/platform/plugins/replica/start/failover',
            titleKey: 'start_replica_failover_title',
            descriptionKey: 'start_replica_failover_description',
        },
        {
            method: 'POST',
            pathPattern: '/private-api/v1/platform/plugins/replica/start/failback',
            titleKey: 'start_replica_failback_title',
            descriptionKey: 'start_replica_failback_description',
        },
        {
            method: 'POST',
            pathPattern: '/private-api/v1/platform/plugins/replica/commit/failback',
            titleKey: 'commit_replica_failback_title',
            descriptionKey: 'commit_replica_failback_description',
        },
        {
            method: 'POST',
            pathPattern: '/private-api/v1/platform/plugins/replica/undo/failover',
            titleKey: 'undo_replica_failover_title',
            descriptionKey: 'undo_replica_failover_description',
        },
        {
            method: 'POST',
            pathPattern: '/private-api/v1/platform/plugins/replica/undo/failback',
            titleKey: 'undo_replica_failback_title',
            descriptionKey: 'undo_replica_failback_description',
        },
    ],
};
