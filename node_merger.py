# -*- coding: utf-8 -*-
import logging
from concurrent.futures import ThreadPoolExecutor
from node_fetcher import NodeFetcher

class NodeMerger:
    """节点合并器，负责合并多个源的节点"""
    
    def __init__(self, config):
        self.config = config
        self.fetcher = NodeFetcher(config)
        self.workers = config.get("WORKERS", 10)
    
    def merge_nodes(self):
        """合并所有节点源"""
        all_nodes = []
        unique_nodes = set()
        
        # 获取所有节点源
        sources = self.config.get("SOURCES", [])
        if not sources:
            logging.error("没有配置节点源")
            return []
        
        logging.info(f"开始合并 {len(sources)} 个节点源")
        
        # 并发获取节点
        try:
            with ThreadPoolExecutor(max_workers=self.workers) as executor:
                results = list(executor.map(self.fetcher.fetch_nodes, sources))
            
            # 合并所有节点并去重
            for nodes in results:
                for node in nodes:
                    if node not in unique_nodes:
                        unique_nodes.add(node)
                        all_nodes.append(node)
            
            logging.info(f"节点合并完成，共获取 {len(all_nodes)} 个唯一节点")
        except Exception as e:
            logging.error(f"合并节点时发生错误: {str(e)}")
            # 尝试串行获取作为备选方案
            all_nodes = self._fetch_nodes_serially(sources)
        
        return all_nodes
    
    def _fetch_nodes_serially(self, sources):
        """串行获取节点，作为并发失败的备选方案"""
        all_nodes = []
        unique_nodes = set()
        
        logging.info("尝试串行获取节点源")
        for url in sources:
            nodes = self.fetcher.fetch_nodes(url)
            for node in nodes:
                if node not in unique_nodes:
                    unique_nodes.add(node)
                    all_nodes.append(node)
        
        logging.info(f"串行获取完成，共获取 {len(all_nodes)} 个唯一节点")
        return all_nodes