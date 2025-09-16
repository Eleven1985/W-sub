# -*- coding: utf-8 -*-
import re
import time
import base64
import logging
import socket
import requests
from concurrent.futures import ThreadPoolExecutor

class NodeSelector:
    """节点选择器，负责测试节点速度并选择最优节点"""
    
    def __init__(self, config):
        self.config = config
        self.test_timeout = config.get("TEST_TIMEOUT", 3)
        self.best_nodes_count = config.get("BEST_NODES_COUNT", 50)
    
    def test_and_select_best_nodes(self, nodes):
        """测试并选择最优节点"""
        if not nodes:
            logging.warning("没有可测试的节点")
            return []
        
        logging.info(f"开始测试 {len(nodes)} 个节点的连接速度")
        
        # 为了避免测试时间过长，限制测试节点数量
        test_nodes = nodes[:200]  # 最多测试200个节点
        
        # 并发测试节点
        node_speeds = []
        try:
            with ThreadPoolExecutor(max_workers=10) as executor:
                results = list(executor.map(self._test_node_speed, test_nodes))
            
            # 收集有效结果 - 只保留响应时间小于测试超时的节点
            for node, speed in results:
                # 只有响应时间小于测试超时时间且不是无限大的节点才被认为有效
                if speed > 0 and speed < float('inf'):
                    node_speeds.append((node, speed))
                    logging.debug(f"节点通过测试，响应时间: {speed:.3f}秒")
            
            # 如果没有足够的有效节点，放宽条件
            if len(node_speeds) < self.best_nodes_count:
                logging.warning(f"有效节点数量不足{self.best_nodes_count}个({len(node_speeds)}个)，尝试使用备用方法选择节点")
                # 备用方法：直接返回原始节点列表的一部分
                return nodes[:self.best_nodes_count]
            
            # 按速度排序（响应时间越短，速度越快）
            node_speeds.sort(key=lambda x: x[1])
            
            # 选择最优节点
            best_count = min(self.best_nodes_count, len(node_speeds))
            best_nodes = [node for node, _ in node_speeds[:best_count]]
            
            logging.info(f"节点测试完成，选择了 {len(best_nodes)} 个最优节点")
            return best_nodes
        except Exception as e:
            logging.error(f"测试节点时发生错误: {str(e)}")
            # 如果测试失败，返回原始节点列表的一部分作为备用
            return nodes[:self.best_nodes_count]
    
    def _test_node_speed(self, node):
        """测试单个节点的连接速度"""
        try:
            # 从节点URL中提取服务器地址
            server = self._extract_server_from_node(node)
            if server:
                start_time = time.time()
                # 使用socket连接测试延迟
                with socket.create_connection((server, 443), timeout=self.test_timeout):
                    response_time = time.time() - start_time
                    logging.debug(f"节点 {server} 响应时间: {response_time:.3f}秒")
                    return (node, response_time)
        except Exception as e:
            logging.debug(f"测试节点失败: {str(e)}")
        
        # 测试失败，返回无限大的延迟
        return (node, float('inf'))
    
    def _extract_server_from_node(self, node):
        """从节点URL中提取服务器地址"""
        try:
            # 尝试解码可能的base64编码
            try:
                # 处理常见的节点格式
                if node.startswith(('vmess://', 'vless://', 'trojan://', 'ss://', 'ssr://', 'hysteria://', 'tuic://')):
                    scheme, encoded = node.split('://', 1)
                    # 尝试解码base64
                    try:
                        # 确保编码字符串长度是4的倍数
                        padding = '=' * ((4 - len(encoded) % 4) % 4)
                        decoded = base64.b64decode(encoded + padding).decode('utf-8', errors='ignore')
                        # 从解码后的内容中提取服务器地址
                        match = re.search(r'(?:server|add|host)[:="]\s*([a-zA-Z0-9.-]+)', decoded)
                        if match:
                            return match.group(1)
                    except Exception as e:
                        logging.debug(f"解码节点内容失败: {str(e)}")
                        pass
                
                # 简单的正则表达式匹配域名或IP（备用方案）
                match = re.search(r'(?:@|://)([a-zA-Z0-9.-]+)', node)
                if match:
                    server = match.group(1)
                    # 移除可能的端口号
                    if ':' in server:
                        server = server.split(':')[0]
                    return server
                
                # 尝试匹配最后一个@符号后面的内容（常见于某些节点格式）
                match = re.search(r'@([a-zA-Z0-9.-]+)', node)
                if match:
                    server = match.group(1)
                    if ':' in server:
                        server = server.split(':')[0]
                    return server
            except Exception as e:
                logging.debug(f"提取服务器地址失败: {str(e)}")
                pass
        except Exception as e:
            logging.debug(f"处理节点时发生异常: {str(e)}")
            pass
        
        # 如果以上方法都失败，返回None
        return None
    
    def generate_best_subscription(self, best_nodes, output_path):
        """生成最优节点订阅文件"""
        try:
            if not best_nodes:
                logging.warning("没有最优节点可生成订阅")
                return None
            
            # 将节点列表转换为字符串并编码
            nodes_text = '\n'.join(best_nodes)
            subscription_content = base64.b64encode(nodes_text.encode('utf-8')).decode('utf-8')
            
            # 保存到文件
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(subscription_content)
            
            logging.info(f"最优节点订阅已生成: {output_path}")
            return subscription_content
        except Exception as e:
            logging.error(f"生成最优节点订阅失败: {str(e)}")
            return None