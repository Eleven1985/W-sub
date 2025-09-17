# -*- coding: utf-8 -*-
import os
import re
import logging

class ConfigLoader:
    """配置加载器，从配置文件读取节点源和其他设置"""
    
    def load_config(self):
        """加载配置，优先使用config/config.txt"""
        # 默认配置
        config = {
            "SOURCES": [],
            "TIMEOUT": 5,
            "OUTPUT_ALL_FILE": "subscription_all.txt",
            "WORKERS": 10,
            "MAX_RETRY": 2
        }
        
        # 预编译URL正则表达式
        url_pattern = re.compile(r'^https?://')
        
        # 尝试多个可能的配置文件路径
        current_dir = os.path.dirname(os.path.abspath(__file__))
        possible_paths = [
            os.path.join(current_dir, "config", "config.txt"),
            os.path.join(current_dir, "config.txt"),
            "config/config.txt",
            "config.txt"
        ]
        
        # 尝试所有可能的路径
        for path in possible_paths:
            try:
                if os.path.exists(path):
                    logging.info(f"尝试加载配置文件: {path}")
                    with open(path, 'r', encoding='utf-8') as f:
                        config["SOURCES"] = []  # 清空源列表
                        
                        for line in f:
                            line = line.strip()
                            if not line or line.startswith('#'):
                                continue
                            
                            # 解析配置项
                            if '=' in line:
                                key, value = line.split('=', 1)
                                key, value = key.strip(), value.strip()
                                
                                if key == "SOURCES" and url_pattern.match(value):
                                    config[key].append(value)
                                elif key in config:
                                    if key in ["TIMEOUT", "WORKERS", "MAX_RETRY"]:
                                        try:
                                            config[key] = int(value)
                                        except ValueError:
                                            logging.warning(f"配置项 {key} 值无效，使用默认值")
                                    else:
                                        config[key] = value
                            # 简化格式：直接识别URL
                            elif url_pattern.match(line):
                                config["SOURCES"].append(line)
                    
                    # 去重节点源，避免重复请求
                    config["SOURCES"] = list(dict.fromkeys(config["SOURCES"]))
                    
                    logging.info(f"成功加载配置文件: {path}")
                    break
            except Exception as e:
                logging.error(f"加载配置文件 {path} 失败: {str(e)}")
        
        # 检查是否有有效的节点源
        if not config["SOURCES"]:
            logging.warning("未找到有效的节点源，请在config.txt中添加节点源URL")
        
        logging.info(f"成功加载配置，共 {len(config['SOURCES'])} 个节点源")
        return config