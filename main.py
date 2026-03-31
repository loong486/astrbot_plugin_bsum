async def fetch_bilibili_subs(self, bvid: str):
        """调用 B 站公开 API 获取视频标题和简介"""
        api_url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
        # 伪装成浏览器，防止被 B 站防火墙拦截
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        # 使用 aiohttp 发起异步网络请求
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, headers=headers) as response:
                if response.status != 200:
                    raise Exception(f"网络请求失败，状态码: {response.status}")
                
                data = await response.json()
                
                # B 站 API 规定，code 为 0 才代表请求成功
                if data.get('code') != 0:
                    raise Exception(f"B站API返回错误: {data.get('message')}")
                    
                video_info = data['data']
                title = video_info['title']
                # 获取视频简介，如果简介为空，则给一个默认提示
                desc = video_info['desc'] if video_info['desc'] else "该视频未提供文字简介。"
                
                # 为了后续使用，我们也可以把封面链接（pic）等信息先打印出来看看
                print(f"成功获取视频: {title}, 封面: {video_info['pic']}")
                
                # 将简介作为我们要总结的文案返回
                return desc, title