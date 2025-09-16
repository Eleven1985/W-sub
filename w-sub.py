# -*- coding: utf-8 -*-
"""
w-sub - 节点订阅汇总工具
功能：
1. 从指定URL获取节点配置
2. 合并多个源的节点
3. 生成包含所有节点的订阅文件
4. 支持按节点类型分类生成订阅文件
5. 测试并选择最优节点
"""
import os
import sys
import re
import base64
import logging
from datetime import datetime
import shutil

# 配置日志
sys.stdout.reconfigure(encoding='utf-8')
# 修改日志配置
logging.basicConfig(
    level=logging.DEBUG,  # 改为DEBUG级别
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("w-sub.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# 导入自定义模块
from config_loader import ConfigLoader
from node_merger import NodeMerger
from node_selector import NodeSelector

class NodeProcessor:
    """节点处理器，负责处理节点和生成订阅文件"""
    
    def __init__(self, config, output_dir=None):
        self.config = config
        self.nodes = []
        # 设置输出目录，默认在当前目录下创建subscriptions文件夹
        self.output_dir = output_dir or "subscriptions"
        # 确保输出目录存在
        self._ensure_output_dir()
    
    def _ensure_output_dir(self):
        """确保输出目录存在"""
        # 使用绝对路径
        absolute_output_dir = os.path.abspath(self.output_dir)
        
        try:
            if not os.path.exists(absolute_output_dir):
                os.makedirs(absolute_output_dir, exist_ok=True)
                logger.info(f"已创建输出目录: {absolute_output_dir}")
            else:
                logger.info(f"输出目录已存在: {absolute_output_dir}")
            self.output_dir = absolute_output_dir
        except Exception as e:
            logger.error(f"创建输出目录失败: {str(e)}")
            # 尝试使用当前目录作为备选
            self.output_dir = os.getcwd()
            logger.warning(f"将使用当前目录作为输出目录: {self.output_dir}")
    
    def _get_output_path(self, filename):
        """获取文件的完整输出路径"""
        return os.path.join(self.output_dir, filename)
    
    # 修改NodeProcessor类的generate_subscription方法
    def generate_subscription(self, nodes, output_file):
        """生成订阅文件"""
        try:
            if not nodes:
                logger.warning(f"没有节点可生成订阅: {output_file}")
                return None
            
            # 获取完整的输出路径
            full_output_path = self._get_output_path(output_file)
            logger.info(f"准备生成订阅文件: {full_output_path}，包含{len(nodes)}个节点")
            
            # 确保输出目录存在
            output_dir = os.path.dirname(full_output_path)
            if output_dir and not os.path.exists(output_dir):
                try:
                    os.makedirs(output_dir, exist_ok=True)
                    logger.info(f"已创建输出目录: {output_dir}")
                except Exception as dir_err:
                    logger.error(f"创建输出目录失败: {str(dir_err)}")
                    # 回退到当前目录
                    full_output_path = os.path.join(os.getcwd(), output_file)
                    logger.warning(f"回退到当前目录生成文件: {full_output_path}")
            
            # 将节点列表转换为字符串并编码
            nodes_text = '\n'.join(nodes)
            subscription_content = base64.b64encode(nodes_text.encode('utf-8')).decode('utf-8')
            
            # 保存到文件
            try:
                with open(full_output_path, 'w', encoding='utf-8') as f:
                    f.write(subscription_content)
                    # 在Windows系统上确保数据写入磁盘
                    if os.name == 'nt':
                        try:
                            os.fsync(f.fileno())
                        except:
                            pass  # Windows可能不支持fsync，忽略错误
                
                # 验证文件是否成功创建
                if os.path.exists(full_output_path):
                    file_size = os.path.getsize(full_output_path)
                    if file_size > 0:
                        logger.info(f"订阅已生成: {full_output_path}，大小: {file_size}字节")
                    else:
                        logger.warning(f"订阅文件为空: {full_output_path}")
                else:
                    logger.error(f"订阅文件创建失败: {full_output_path}")
                
                return subscription_content
            except Exception as file_err:
                logger.error(f"写入文件失败: {str(file_err)}")
                # 尝试创建一个简单的测试文件来验证写入权限
                test_file = os.path.join(os.getcwd(), "test_write_permission.txt")
                try:
                    with open(test_file, 'w', encoding='utf-8') as f:
                        f.write("test")
                    if os.path.exists(test_file):
                        logger.info(f"写入权限测试成功，可以在当前目录创建文件")
                        os.remove(test_file)  # 清理测试文件
                    return None
                except Exception as perm_err:
                    logger.error(f"当前目录也没有写入权限: {str(perm_err)}")
                    return None
        except Exception as e:
            logger.error(f"生成订阅文件时发生未预期错误: {str(e)}")
            import traceback
            traceback.print_exc()
            return None
    
    def categorize_nodes_by_type(self):
        """按节点类型分类节点"""
        categorized_nodes = {
            'vmess': [],
            'v2ray': [],
            'trojan': [],
            'shadowsocks': [],
            'shadowsocksr': [],
            'vless': [],
            'ss': [],
            'ssr': [],
            'hysteria': [],
            # 添加更多节点类型
            'tuic': [],
            'naiveproxy': [],
            'socks5': [],
            'http': [],
            'https': [],
            'wireguard': [],
            'sing-box': [],
            'clash': [],
            'xray': [],
            'other': []
        }
        
        for node in self.nodes:
            if node.startswith('vmess://'):
                categorized_nodes['vmess'].append(node)
            elif node.startswith('v2ray://'):
                categorized_nodes['v2ray'].append(node)
            elif node.startswith('trojan://') or node.startswith('trojan-go://'):
                categorized_nodes['trojan'].append(node)
            elif node.startswith('shadowsocks://'):
                categorized_nodes['shadowsocks'].append(node)
            elif node.startswith('shadowsocksr://'):
                categorized_nodes['shadowsocksr'].append(node)
            elif node.startswith('vless://'):
                categorized_nodes['vless'].append(node)
            elif node.startswith('ss://'):
                categorized_nodes['ss'].append(node)
            elif node.startswith('ssr://'):
                categorized_nodes['ssr'].append(node)
            elif node.startswith('hysteria://'):
                categorized_nodes['hysteria'].append(node)
            # 添加新的节点类型判断
            elif node.startswith('tuic://'):
                categorized_nodes['tuic'].append(node)
            elif node.startswith('naiveproxy://'):
                categorized_nodes['naiveproxy'].append(node)
            elif node.startswith('socks5://'):
                categorized_nodes['socks5'].append(node)
            elif node.startswith('http://'):
                categorized_nodes['http'].append(node)
            elif node.startswith('https://'):
                categorized_nodes['https'].append(node)
            elif node.startswith('wireguard://'):
                categorized_nodes['wireguard'].append(node)
            elif node.startswith('sing-box://'):
                categorized_nodes['sing-box'].append(node)
            elif node.startswith('clash://'):
                categorized_nodes['clash'].append(node)
            elif node.startswith('xray://'):
                categorized_nodes['xray'].append(node)
            else:
                categorized_nodes['other'].append(node)
        
        # 记录分类结果
        for node_type, nodes_list in categorized_nodes.items():
            if nodes_list:
                logger.info(f"{node_type.upper()} 类型节点数量: {len(nodes_list)}")
        
        return categorized_nodes
    
    def generate_category_subscriptions(self):
        """为每种节点类型生成订阅文件"""
        categorized_nodes = self.categorize_nodes_by_type()
        
        # 定义节点类型到文件名的映射
        type_to_filename = {
            'vmess': 'subscription_vmess.txt',
            'v2ray': 'subscription_v2ray.txt',
            'trojan': 'subscription_trojan.txt',
            'shadowsocks': 'subscription_shadowsocks.txt',
            'shadowsocksr': 'subscription_shadowsocksr.txt',
            'vless': 'subscription_vless.txt',
            'ss': 'subscription_ss.txt',
            'ssr': 'subscription_ssr.txt',
            'hysteria': 'subscription_hysteria.txt',
            # 添加新的节点类型文件名映射
            'tuic': 'subscription_tuic.txt',
            'naiveproxy': 'subscription_naiveproxy.txt',
            'socks5': 'subscription_socks5.txt',
            'http': 'subscription_http.txt',
            'https': 'subscription_https.txt',
            'wireguard': 'subscription_wireguard.txt',
            'sing-box': 'subscription_sing-box.txt',
            'clash': 'subscription_clash.txt',
            'xray': 'subscription_xray.txt',
            'other': 'subscription_other.txt'
        }
        
        # 为每种类型生成订阅文件
        for node_type, nodes_list in categorized_nodes.items():
            if nodes_list:
                filename = type_to_filename[node_type]
                self.generate_subscription(nodes_list, filename)
        
        logger.info("所有节点类型的订阅文件已生成完成")
    
    def generate_best_nodes_subscription(self):
        """生成最优节点订阅"""
        try:
            # 创建NodeSelector实例
            selector = NodeSelector(self.config)
            
            # 测试并选择最优节点
            best_nodes = selector.test_and_select_best_nodes(self.nodes)
            
            if not best_nodes:
                logger.warning("没有选择到最优节点，尝试使用原始节点列表")
                best_nodes = self.nodes[:self.config.get("BEST_NODES_COUNT", 50)]
            
            logger.info(f"准备生成优选节点订阅，共{len(best_nodes)}个节点")
            
            # 生成最优节点订阅文件 - 主方法
            output_path = self._get_output_path(self.config["OUTPUT_BEST_FILE"])
            logger.debug(f"输出路径: {output_path}")
            
            # 直接使用当前类的generate_subscription方法，这个方法更可靠
            result = self.generate_subscription(best_nodes, self.config["OUTPUT_BEST_FILE"])
            
            if result is None:
                logger.error("生成最优节点订阅失败，尝试在当前目录创建文件")
                # 直接在当前目录创建文件作为最后备用
                try:
                    nodes_text = '\n'.join(best_nodes)
                    subscription_content = base64.b64encode(nodes_text.encode('utf-8')).decode('utf-8')
                    
                    fallback_path = os.path.join(os.getcwd(), self.config["OUTPUT_BEST_FILE"])
                    with open(fallback_path, 'w', encoding='utf-8') as f:
                        f.write(subscription_content)
                    
                    if os.path.exists(fallback_path) and os.path.getsize(fallback_path) > 0:
                        logger.info(f"已在当前目录生成最优节点订阅: {fallback_path}")
                    else:
                        logger.error("在当前目录创建文件也失败")
                except Exception as e:
                    logger.error(f"备用方法创建文件失败: {str(e)}")
            
            return best_nodes
        except Exception as e:
            logger.error(f"生成最优节点订阅时发生错误: {str(e)}")
            import traceback
            traceback.print_exc()
            # 返回空列表
            return []

# 在main函数前添加命令行参数解析
import argparse

def main():
    # 添加命令行参数解析
    parser = argparse.ArgumentParser(description='w-sub 节点订阅汇总工具')
    parser.add_argument('--output', '-o', default='.', help='输出目录，默认为当前目录')
    args = parser.parse_args()
    
    logger.info("=== w-sub 节点订阅汇总工具启动 ===")
    logger.info(f"当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"输出目录: {args.output}")
    
    try:
        # 加载配置
        config_loader = ConfigLoader()
        config = config_loader.load_config()
        
        # 创建处理器实例，使用命令行参数指定的输出目录
        processor = NodeProcessor(config, args.output)
        
        # 创建合并器实例并执行处理流程
        merger = NodeMerger(config)
        processor.nodes = merger.merge_nodes()
        
        if not processor.nodes:
            logger.error("未能获取任何节点，请检查网络连接或源地址是否有效")
            return
        
        # 生成包含所有节点的订阅文件
        processor.generate_subscription(processor.nodes, config["OUTPUT_ALL_FILE"])
        
        # 生成最优节点订阅文件
        processor.generate_best_nodes_subscription()
        
        # 按节点类型生成分类订阅文件
        processor.generate_category_subscriptions()
        
        logger.info(f"=== w-sub 节点订阅汇总工具运行完成 ===")
        logger.info(f"所有节点处理完成，共生成{len(processor.nodes)}个节点的订阅")
    except Exception as e:
        logger.error(f"程序运行出错: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()