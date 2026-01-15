from kubernetes import client, config
import logging

logger = logging.getLogger(__name__)

def get_cluster_status():
    """Fetches high-level cluster health (Nodes & Pods) using the K8s API."""
    try:
        # Load in-cluster config if running in K8s, otherwise local kubeconfig
        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()

        v1 = client.CoreV1Api()
        
        # 1. Fetch Nodes
        nodes = v1.list_node()
        node_status = []
        for n in nodes.items:
            condition = next((c for c in n.status.conditions if c.type == "Ready"), None)
            node_status.append({
                "name": n.metadata.name,
                "status": "Online" if condition and condition.status == "True" else "Offline",
                "role": "master" if "node-role.kubernetes.io/control-plane" in n.metadata.labels else "worker"
            })

        # 2. Fetch Pods count in iooding namespace
        pods = v1.list_namespaced_pod(namespace="iooding")
        healthy_pods = len([p for p in pods.items if p.status.phase == "Running"])
        total_pods = len(pods.items)

        return {
            "nodes": node_status,
            "iooding_service": f"{healthy_pods}/{total_pods} Pods healthy",
            "global_status": "Healthy" if all(n["status"] == "Online" for n in node_status) else "Degraded"
        }
    except Exception as e:
        logger.error(f"Failed to fetch K8s status: {e}")
        return {
            "nodes": [],
            "iooding_service": "API Unreachable",
            "global_status": "Maintenance"
        }
