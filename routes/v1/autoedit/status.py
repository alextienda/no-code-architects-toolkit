# Copyright (c) 2025 Stephen G. Pope
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

"""
AutoEdit Status Endpoint
Check the status of an AutoEdit job and retrieve the output URL when complete.
"""

from flask import Blueprint, jsonify
from services.authentication import authenticate
from google.cloud import workflows_v1
from google.cloud.workflows import executions_v1
from google.cloud.workflows.executions_v1 import Execution
from google.oauth2 import service_account
import logging
import os
import json

v1_autoedit_status_bp = Blueprint('v1_autoedit_status', __name__)
logger = logging.getLogger(__name__)

# AutoEdit configuration
GCP_PROJECT = "autoedit-at"
WORKFLOW_NAME = "autoedit-aroll-flow"
WORKFLOW_LOCATION = "us-central1"


def get_credentials():
    """Get GCP credentials."""
    gcp_sa_credentials = os.environ.get('GCP_SA_CREDENTIALS')
    if gcp_sa_credentials:
        try:
            creds_dict = json.loads(gcp_sa_credentials)
            return service_account.Credentials.from_service_account_info(creds_dict)
        except Exception as e:
            logger.warning(f"Failed to use GCP_SA_CREDENTIALS: {e}")
    return None


def get_workflow_executions(limit=50):
    """Get recent workflow executions."""
    credentials = get_credentials()
    client = executions_v1.ExecutionsClient(credentials=credentials)

    parent = f"projects/{GCP_PROJECT}/locations/{WORKFLOW_LOCATION}/workflows/{WORKFLOW_NAME}"

    # List recent executions
    executions = []
    try:
        request = executions_v1.ListExecutionsRequest(
            parent=parent,
            page_size=limit
        )
        page_result = client.list_executions(request=request)
        for execution in page_result:
            executions.append(execution)
    except Exception as e:
        logger.error(f"Error listing executions: {e}")

    return executions


def get_execution_details(execution_name):
    """Get detailed execution info including result."""
    credentials = get_credentials()
    client = executions_v1.ExecutionsClient(credentials=credentials)

    try:
        request = executions_v1.GetExecutionRequest(name=execution_name)
        execution = client.get_execution(request=request)
        return execution
    except Exception as e:
        logger.error(f"Error getting execution {execution_name}: {e}")
        return None


def find_execution_by_filename(filename):
    """Find a workflow execution that processed a specific filename."""
    executions = get_workflow_executions(limit=100)

    # The filename in the workflow is stored in the argument
    target_filename = filename if filename.endswith('.mp4') else f"{filename}.mp4"

    for execution in executions:
        try:
            # Check the execution argument for the filename
            if execution.argument:
                arg_data = json.loads(execution.argument)
                if arg_data.get('data', {}).get('name') == target_filename:
                    return execution
        except Exception as e:
            logger.debug(f"Error parsing execution argument: {e}")
            continue

    return None


def parse_execution_result(execution):
    """Parse execution result to extract relevant info."""
    status_map = {
        Execution.State.ACTIVE: "processing",
        Execution.State.SUCCEEDED: "completed",
        Execution.State.FAILED: "failed",
        Execution.State.CANCELLED: "cancelled",
    }

    status = status_map.get(execution.state, "unknown")

    result = {
        "execution_id": execution.name.split('/')[-1],
        "status": status,
        "start_time": execution.start_time.isoformat() if execution.start_time else None,
        "end_time": execution.end_time.isoformat() if execution.end_time else None,
    }

    if execution.state == Execution.State.SUCCEEDED and execution.result:
        try:
            result_data = json.loads(execution.result)
            result["output_url"] = result_data.get("output_url")
            result["original_file"] = result_data.get("original_file")
            result["segments_kept"] = result_data.get("segments_kept")
            result["duration_kept_seconds"] = result_data.get("duration_kept_seconds")
        except Exception as e:
            logger.error(f"Error parsing execution result: {e}")
            result["raw_result"] = execution.result

    if execution.state == Execution.State.FAILED and execution.error:
        result["error"] = {
            "message": execution.error.message if execution.error else "Unknown error",
            "context": execution.error.context if execution.error else None
        }

    return result


@v1_autoedit_status_bp.route('/v1/autoedit/status/<job_id>', methods=['GET'])
@authenticate
def autoedit_status(job_id):
    """
    Check the status of an AutoEdit job.

    Args:
        job_id: The job ID returned from /v1/autoedit/upload

    Returns:
        JSON with status and output_url when complete
    """
    logger.info(f"Checking AutoEdit status for job: {job_id}")

    try:
        # Find the execution for this filename
        execution = find_execution_by_filename(job_id)

        if not execution:
            # Check if maybe it's still being triggered (workflow not started yet)
            return jsonify({
                "job_id": job_id,
                "status": "pending",
                "message": "Workflow execution not found yet. It may still be starting (wait up to 2 minutes after upload)."
            }), 200

        # Get detailed execution info
        detailed = get_execution_details(execution.name)
        if detailed:
            execution = detailed

        result = parse_execution_result(execution)
        result["job_id"] = job_id

        logger.info(f"AutoEdit status for {job_id}: {result['status']}")
        return jsonify(result), 200

    except Exception as e:
        error_msg = f"Error checking status: {str(e)}"
        logger.error(f"Job {job_id}: {error_msg}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({"error": error_msg, "job_id": job_id}), 500


@v1_autoedit_status_bp.route('/v1/autoedit/jobs', methods=['GET'])
@authenticate
def autoedit_list_jobs():
    """
    List recent AutoEdit jobs.

    Returns:
        JSON array of recent job statuses
    """
    logger.info("Listing recent AutoEdit jobs")

    try:
        executions = get_workflow_executions(limit=20)

        jobs = []
        for execution in executions:
            try:
                result = parse_execution_result(execution)

                # Try to extract filename from argument
                if execution.argument:
                    arg_data = json.loads(execution.argument)
                    result["filename"] = arg_data.get('data', {}).get('name', 'unknown')

                jobs.append(result)
            except Exception as e:
                logger.debug(f"Error parsing execution: {e}")
                continue

        return jsonify({
            "jobs": jobs,
            "total": len(jobs)
        }), 200

    except Exception as e:
        error_msg = f"Error listing jobs: {str(e)}"
        logger.error(error_msg)
        return jsonify({"error": error_msg}), 500
