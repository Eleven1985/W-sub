# -*- coding: utf-8 -*-
"""
node_merger - 节点合并模块
功能：合并多个源的节点，支持并发处理和去重
"""
import os
import logging
import concurrent.futures
from node_fetcher import NodeFetcher

# 配置日志
logger = logging.getLogger(__name__)

class NodeMerger:
    """节点合并器，负责从多个源获取并合并节点"""
    def __init__(self, config):
        self.config = config
        self.nodes = []
        # 确保配置中有必要的键
        if 'MAX_RETRY' not in self.config:
            self.config['MAX_RETRY'] = 2
        if 'WORKERS' not in self.config:
            self.config['WORKERS'] = 10
        if 'TIMEOUT' not in self.config:
            self.config['TIMEOUT'] = 5
            
        self.fetcher = NodeFetcher(self.config)
    
    def merge_nodes(self):
        """合并所有源的节点"""
        if not self.config.get("SOURCES"):
            logger.error("没有可用的节点源，无法合并节点")
            return []
        
        all_nodes = []
        total_extracted = 0
        success_count = 0
        failed_count = 0
        
        # 并发获取所有源的节点
        try:
            logger.info(f"开始并发获取{len(self.config['SOURCES'])}个节点源，使用{self.config.get('WORKERS', 10)}个工作线程")
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.config.get('WORKERS', 10)) as executor:
                # 创建任务列表
                futures = {executor.submit(self.fetcher.fetch_nodes, url): url for url in self.config["SOURCES"]}
                
                # 收集结果
                for future in concurrent.futures.as_completed(futures):
                    url = futures[future]
                    try:
                        nodes = future.result()
                        if nodes:
                            total_extracted += len(nodes)
                            all_nodes.extend(nodes)
                            success_count += 1
                            logger.info(f"成功获取节点源 {url} 的节点")
                        else:
                            failed_count += 1
                            logger.warning(f"节点源 {url} 未返回任何节点")
                    except Exception as e:
                        failed_count += 1
                        logger.error(f"处理节点源 {url} 时发生异常: {str(e)}")
        except Exception as e:
            logger.error(f"并发获取节点源时发生异常: {str(e)}")
            # 尝试使用备用方法获取节点
            logger.info("尝试使用串行方法获取节点源")
            for url in self.config["SOURCES"]:
                try:
                    nodes = self.fetcher.fetch_nodes(url)
                    if nodes:
                        total_extracted += len(nodes)
                        all_nodes.extend(nodes)
                        success_count += 1
                    else:
                        failed_count += 1
                except Exception as inner_e:
                    failed_count += 1
                    logger.error(f"获取节点源 {url} 失败: {str(inner_e)}")
        
        # 去重
        self.nodes = list(set(all_nodes))
        logger.info(f"合并后共获取到{len(self.nodes)}个唯一节点 (总提取: {total_extracted}个节点)")
        logger.info(f"去重后减少了{total_extracted - len(self.nodes)}个重复节点")
        logger.info(f"节点源获取结果：成功 {success_count} 个，失败 {failed_count} 个")
        
        return self.nodes