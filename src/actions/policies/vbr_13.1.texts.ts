/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

// Ported from veeam-intelligence frontend/agents/src/localization/_common/vbr/fetchPolicy/en.i18n.ts
export const vbr_13_1_FetchPolicyTexts: Record<string, string> = {
    enable_proxy_title: 'Enable this backup proxy?',
    enable_proxy_description:
        'Veeam Intelligence wants to re-enable the selected backup proxy so it can process backup tasks again. This is a configuration change that returns the proxy to the backup pool.',

    disable_proxy_title: 'Disable this backup proxy?',
    disable_proxy_description:
        'Veeam Intelligence wants to disable the selected backup proxy. The proxy is removed from the backup pool, and if all proxies are disabled, backups can stop running.',

    enable_repository_maintenance_mode_title: 'Enable Maintenance mode on this scale-out repository?',
    enable_repository_maintenance_mode_description:
        'Veeam Intelligence wants to enable Maintenance mode on the selected scale-out backup repository extents. The extents are taken offline, and backups targeting them will fail until Maintenance mode is disabled.',

    disable_repository_maintenance_mode_title: 'Disable Maintenance mode on this scale-out repository?',
    disable_repository_maintenance_mode_description:
        'Veeam Intelligence wants to disable Maintenance mode on the selected scale-out backup repository extents and bring them back online. This can trigger retention catch-up and data evacuation on the affected extents.',

    enable_repository_sealed_mode_title: 'Enable Sealed mode on this scale-out repository?',
    enable_repository_sealed_mode_description:
        'Veeam Intelligence wants to enable Sealed mode on the selected scale-out backup repository extents. No new backups are written to the sealed extents, and existing backups expire over time according to retention.',

    disable_repository_sealed_mode_title: 'Disable Sealed mode on this scale-out repository?',
    disable_repository_sealed_mode_description:
        'Veeam Intelligence wants to disable Sealed mode on the selected scale-out backup repository extents. Retention can then act on the stored backups, which may lead to data being deleted.',

    disable_job_title: 'Disable this backup job?',
    disable_job_description:
        'Veeam Intelligence wants to disable the selected job. The job stays disabled and will not run on its schedule until it is re-enabled.',

    enable_job_title: 'Enable this backup job?',
    enable_job_description:
        'Veeam Intelligence wants to enable the selected job. The job will resume running on its schedule, but it will not start a run right now.',

    start_job_title: 'Start this backup job?',
    start_job_description:
        'Veeam Intelligence wants to start the selected job. An active full run can fill the target repository, and chained jobs may cascade downstream when enabled.',

    stop_job_title: 'Stop this backup job?',
    stop_job_description:
        'Veeam Intelligence wants to stop the selected running job. The current incremental run is lost and will need to be started again.',

    retry_job_title: 'Retry this backup job?',
    retry_job_description:
        'Veeam Intelligence wants to retry the selected failed job. This starts another run of the job, consuming backup infrastructure resources.',

    install_license_title: 'Install this license?',
    install_license_description:
        'Veeam Intelligence wants to install a license on the backup server. This can downgrade the current license or detach the server from Veeam Backup Enterprise Manager.',

    revoke_capacity_license_title: 'Revoke this capacity license?',
    revoke_capacity_license_description:
        'Veeam Intelligence wants to revoke the capacity instance from an unstructured data workload (file share or object storage). The workload becomes unprotected and cannot be backed up until a license is reassigned.',

    revoke_instance_license_title: 'Revoke this instance license?',
    revoke_instance_license_description:
        'Veeam Intelligence wants to revoke the instance license from the selected workload. The workload becomes unprotected and cannot be backed up until a license is reassigned.',

    revoke_socket_license_title: 'Revoke this socket license?',
    revoke_socket_license_description:
        'Veeam Intelligence wants to revoke the socket license from the selected host. The entire host loses its license, and its workloads cannot be backed up until a license is reassigned.',

    scan_backup_title: 'Scan backups with antivirus or YARA rules?',
    scan_backup_description:
        'Veeam Intelligence wants to scan the selected backups with antivirus or YARA rules. This starts a SureBackup session and can generate heavy I/O on the backup infrastructure.',

    migrate_instant_recovery_vm_title: 'Migrate this Instant Recovery VM?',
    migrate_instant_recovery_vm_description:
        'Veeam Intelligence wants to start migrating the VMware vSphere VM that is running from Instant Recovery to permanent storage. This finalizes the restore and cannot be undone.',

    unmount_instant_recovery_vm_title: 'Stop publishing this Instant Recovery VM?',
    unmount_instant_recovery_vm_description:
        'Veeam Intelligence wants to stop publishing the VMware vSphere VM that is running from Instant Recovery and unmount it from the host. The Instant Recovery VM is destroyed if it has not been migrated, and any changes made since the mount are lost.',

    restore_file_share_title: 'Restore this entire file share?',
    restore_file_share_description:
        'Veeam Intelligence wants to restore the entire file share to the original or another location. This can overwrite existing files at the destination with the backed-up state.',

    restore_object_storage_title: 'Restore this entire object storage bucket?',
    restore_object_storage_description:
        'Veeam Intelligence wants to restore the entire object storage bucket or container to the original or another location. This can overwrite existing objects at the destination with the backed-up state.',

    restore_vm_title: 'Restore this entire VMware vSphere VM?',
    restore_vm_description:
        'Veeam Intelligence wants to perform an entire VM restore of a VMware vSphere VM. Restoring to the original location can overwrite the production VM with the backed-up state.',

    start_instant_recovery_vm_title: 'Start Instant Recovery of this VMware vSphere VM?',
    start_instant_recovery_vm_description:
        'Veeam Intelligence wants to start Instant Recovery of a VMware vSphere VM, publishing it directly from the backup. Recovering to the original location can affect the existing production VM.',

    update_license_title: 'Update the installed license?',
    update_license_description:
        'Veeam Intelligence wants to update the license installed on the backup server. This can change the licensed edition or capacity and affect which features remain available.',

    set_license_autoupdate_title: 'Change license auto-update?',
    set_license_autoupdate_description:
        'Veeam Intelligence wants to enable or disable automatic license updates on the backup server. This changes whether the license is refreshed automatically from Veeam.',

    set_unlicensed_agent_consumption_title: 'Change instance consumption for unlicensed agents?',
    set_unlicensed_agent_consumption_description:
        'Veeam Intelligence wants to enable or disable instance license consumption for unlicensed agents. This changes whether such agents consume license instances and can leave workloads unprotected.',

    remove_instance_license_title: 'Remove this instance license?',
    remove_instance_license_description:
        'Veeam Intelligence wants to remove the instance license from the selected workload. The workload becomes unprotected and cannot be backed up until a license is reassigned.',

    install_datacenter_license_title: 'Install this Veeam Data Cloud license?',
    install_datacenter_license_description:
        'Veeam Intelligence wants to install a Veeam Data Cloud (datacenter) license on the backup server. This can change the licensed edition or capacity and affect which features remain available.',

    analyze_encryption_title: 'Start malware encryption analysis?',
    analyze_encryption_description:
        'Veeam Intelligence wants to start malware encryption analysis on the selected restore points. This scans backups for signs of encryption and can generate heavy I/O on the backup infrastructure.',

    migrate_instant_recovery_hyperv_vm_title: 'Migrate this Instant Recovery Hyper-V VM?',
    migrate_instant_recovery_hyperv_vm_description:
        'Veeam Intelligence wants to start migrating the Microsoft Hyper-V VM that is running from Instant Recovery to permanent storage. This finalizes the restore and cannot be undone.',

    unmount_instant_recovery_hyperv_vm_title: 'Stop publishing this Instant Recovery Hyper-V VM?',
    unmount_instant_recovery_hyperv_vm_description:
        'Veeam Intelligence wants to stop publishing the Microsoft Hyper-V VM that is running from Instant Recovery and unmount it from the host. The Instant Recovery VM is destroyed if it has not been migrated, and any changes made since the mount are lost.',

    restore_hyperv_vm_title: 'Restore this entire Microsoft Hyper-V VM?',
    restore_hyperv_vm_description:
        'Veeam Intelligence wants to perform an entire VM restore of a Microsoft Hyper-V VM. Restoring to the original location can overwrite the production VM with the backed-up state.',

    restore_ad_forest_title: 'Start this Active Directory forest restore?',
    restore_ad_forest_description:
        'Veeam Intelligence wants to start an Active Directory forest recovery. This is a major operation that can overwrite domain controllers and directory data at the destination.',

    start_instant_recovery_session_title: 'Start this Instant Recovery session?',
    start_instant_recovery_session_description:
        'Veeam Intelligence wants to start an Instant Recovery session, publishing a workload directly from the backup. Recovering to the original location can affect existing production workloads.',

    upgrade_agent_title: 'Upgrade the agent on this machine?',
    upgrade_agent_description:
        'Veeam Intelligence wants to upgrade the Veeam agent installed on the discovered machine. The agent software is replaced, which may briefly interrupt protection on that machine.',

    install_product_updates_title: 'Install product updates on the backup server?',
    install_product_updates_description:
        'Veeam Intelligence wants to install available updates on the backup server. This can restart services and interrupt running jobs while the update is applied.',

    start_replication_session_title: 'Start this replication job session?',
    start_replication_session_description:
        'Veeam Intelligence wants to start the selected replication job session. This consumes backup infrastructure resources and begins replicating data to the target.',

    stop_replication_session_title: 'Stop this replication job session?',
    stop_replication_session_description:
        'Veeam Intelligence wants to stop the selected running replication job session. The current run is interrupted and will need to be started again.',

    cancel_vm_replication_task_title: 'Cancel this VM replication task?',
    cancel_vm_replication_task_description:
        'Veeam Intelligence wants to cancel the selected VM replication task. The task stops before completing, and the replica may be left in an incomplete state.',

    start_vm_replication_task_title: 'Start this VM replication task?',
    start_vm_replication_task_description:
        'Veeam Intelligence wants to start the selected VM replication task. This replicates the VM to the target host and consumes backup infrastructure resources.',

    start_replica_failover_title: 'Fail over to this replica?',
    start_replica_failover_description:
        'Veeam Intelligence wants to fail over to the selected replica, switching workloads from the production VM to the replica. This affects the production workload and should be coordinated with a disaster recovery plan.',

    start_replica_failback_title: 'Start failback from this replica?',
    start_replica_failback_description:
        'Veeam Intelligence wants to start failback from the selected replica to the production VM. This transfers changes back to production and can overwrite the original VM with the replica state.',

    commit_replica_failback_title: 'Commit this replica failback?',
    commit_replica_failback_description:
        'Veeam Intelligence wants to commit the failback for the selected replica, finalizing the return of workloads to production. This cannot be undone.',

    undo_replica_failover_title: 'Undo this replica failover?',
    undo_replica_failover_description:
        'Veeam Intelligence wants to undo the failover for the selected replica, switching workloads back to the production VM and discarding changes made on the replica during failover.',

    undo_replica_failback_title: 'Undo this replica failback?',
    undo_replica_failback_description:
        'Veeam Intelligence wants to undo the failback for the selected replica, returning workloads to the replica and discarding changes made on production since failback started.',

    collect_job_logs_title: 'Collect logs for this job?',
    collect_job_logs_description:
        'Veeam Intelligence wants to collect the support logs for the selected job and upload them to Veeam Intelligence Cloud for the analysis. This packages diagnostic log data from the backup server and transfers it for processing.',

    update_managed_server_components_title: 'Update components on these managed servers?',
    update_managed_server_components_description:
        'Veeam Intelligence wants to update the Veeam components on the selected managed servers. This restarts the transport and data-mover services on those hosts and fails any tasks currently running on them.',
};
