import os
import json
import boto3
import time
from typing import Dict, List
from isolation.backend import IsolationBackend
from utils.logger import logger

class ECSBackend(IsolationBackend):
    """
    AWS ECS-based isolation backend.
    Launches an ephemeral Fargate task to execute a single User Story.
    This provides true hardware isolation and horizontal scalability.
    """
    
    def __init__(self):
        """
        Initializes the ECS client.
        Expects AWS_REGION, ECS_CLUSTER, and ECS_TASK_DEFINITION in env.
        """
        self.region = os.getenv("AWS_REGION", "us-east-1")
        self.cluster = os.getenv("ECS_CLUSTER", "ada-cluster")
        self.task_definition = os.getenv("ECS_TASK_DEFINITION", "ada-worker-task")
        self.subnets = os.getenv("ECS_SUBNETS", "").split(",")
        self.security_groups = os.getenv("ECS_SECURITY_GROUPS", "").split(",")
        
        self.ecs = boto3.client("ecs", region_name=self.region)
        self.task_arn = None

    def setup(self, story: Dict, repo_path: str) -> None:
        """
        Setup for ECS execution. 
        In production, this might involve uploading the current repo state 
        to S3 or ensuring the task can clone the repo itself.
        """
        logger.info("ECSBackend", f"Preparing ECS execution for story: {story.get('story_id')}")
        # Placeholder for complex setup (S3 uploads, etc.)
        pass

    def execute(self, story: Dict, repo_path: str) -> bool:
        """
        Run the story in an ephemeral ECS Fargate container.
        """
        logger.info("ECSBackend", f"Launching ECS Task on cluster {self.cluster}...")
        
        try:
            # Inject story and repo info as environment overrides
            overrides = {
                'containerOverrides': [
                    {
                        'name': 'ada-worker', # Must match container name in task definition
                        'environment': [
                            {'name': 'STORY_PAYLOAD', 'value': json.dumps(story)},
                            {'name': 'REPO_URL', 'value': repo_path}, # Or an S3 URL
                            {'name': 'RUN_MODE', 'value': 'ECS_WORKER'}
                        ]
                    }
                ]
            }
            
            response = self.ecs.run_task(
                cluster=self.cluster,
                launchType='FARGATE',
                taskDefinition=self.task_definition,
                count=1,
                platformVersion='LATEST',
                networkConfiguration={
                    'awsvpcConfiguration': {
                        'subnets': self.subnets,
                        'securityGroups': self.security_groups,
                        'assignPublicIp': 'ENABLED'
                    }
                },
                overrides=overrides
            )
            
            if not response['tasks']:
                logger.error("ECSBackend", f"Failed to launch ECS task: {response.get('failures')}")
                return False
                
            self.task_arn = response['tasks'][0]['taskArn']
            logger.info("ECSBackend", f"Task launched successfully: {self.task_arn}")
            
            # Wait for completion (Simple polling for now)
            # In a real high-throughput system, we would use webhooks or EventBridge
            return self._wait_for_task()
            
        except Exception as e:
            logger.exception(f"Fatal error launching ECS task: {e}")
            return False

    def _wait_for_task(self) -> bool:
        """Polls ECS for task completion."""
        max_wait = 1200  # 20 minutes
        waited = 0
        while waited < max_wait:
            time.sleep(15)
            waited += 15
            
            desc = self.ecs.describe_tasks(cluster=self.cluster, tasks=[self.task_arn])
            status = desc['tasks'][0]['lastStatus']
            logger.info("ECSBackend", f"Task {self.task_arn} is {status}...")
            
            if status == 'STOPPED':
                exit_code = desc['tasks'][0]['containers'][0].get('exitCode', 1)
                reason = desc['tasks'][0].get('stoppedReason', 'Unknown')
                logger.info("ECSBackend", f"Task stopped. Exit Code: {exit_code}, Reason: {reason}")
                return exit_code == 0
                
        logger.error("ECSBackend", "ECS Task timed out.")
        return False

    def cleanup(self) -> None:
        """Cleanup resources if necessary."""
        pass

    def get_name(self) -> str:
        return "AWS ECS (Fargate)"
