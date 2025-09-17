# -*- coding: utf-8 -*-
"""
修复订阅文件格式，使其兼容v2ray软件
"""
import os
import base64
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def fix_subscription_file(input_file, output_file=None):
    """修复订阅文件格式"""
    if not os.path.exists(input_file):
        logger.error(f"输入文件不存在: {input_file}")
        return False
    
    if not output_file:
        output_file = input_file + '.fixed'
    
    try:
        # 读取原始订阅文件
        with open(input_file, 'r', encoding='utf-8') as f:
            original_content = f.read().strip()
        
        # 尝试解码原始内容（如果已经是Base64编码的）
        try:
            # 修复可能的填充问题
            missing_padding = len(original_content) % 4
            if missing_padding:
                original_content += '=' * (4 - missing_padding)
            
            # 解码内容
            decoded_content = base64.b64decode(original_content).decode('utf-8')
            logger.info(f"成功解码原始订阅文件，包含 {len(decoded_content.split('\n'))} 个节点")
        except Exception as e:
            logger.warning(f"无法解码原始内容，假设它是明文节点列表: {str(e)}")
            decoded_content = original_content
        
        # 确保节点列表格式正确（每行一个节点）
        nodes = [line.strip() for line in decoded_content.split('\n') if line.strip()]
        
        if not nodes:
            logger.error("没有找到有效的节点")
            return False
        
        # 重新生成标准的Base64编码订阅文件
        # 使用\r\n作为行分隔符，确保跨平台兼容性
        nodes_text = '\r\n'.join(nodes)
        fixed_content = base64.b64encode(nodes_text.encode('utf-8')).decode('utf-8')
        
        # 保存修复后的内容
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(fixed_content)
        
        logger.info(f"订阅文件已修复并保存到: {output_file}")
        logger.info(f"包含 {len(nodes)} 个节点")
        return True
    except Exception as e:
        logger.error(f"修复订阅文件时发生错误: {str(e)}")
        return False

if __name__ == "__main__":
    input_path = os.path.join("subscriptions_output", "subscription_all.txt")
    fix_subscription_file(input_path)