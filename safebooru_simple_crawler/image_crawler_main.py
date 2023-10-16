import os
import threading
import time

import requests
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By
from tqdm import tqdm

SEARCH_RESULT_URL_PREFIX = "https://safebooru.org/index.php?page=post&s=list&tags="
POST_VWR_URL_PREFIX = "https://safebooru.org/index.php?page=post&s=view&id="
CURRENT_DIRECTORY = os.path.dirname(os.path.abspath(__file__))
SAVE_DIRECTORY_PREFIX = CURRENT_DIRECTORY + r'\DownloadedPic\\'[:-1]

option = Options()
option.add_argument("--headless")
option.add_argument('--log-level=3')
option.add_experimental_option('excludeSwitches', ['enable-logging'])  # 防止程序运行时在控制台输出调试信息


def is_duplicate(target: str, target_hash_list: dict):
    if target in target_hash_list:
        return target_hash_list[target]
    else:
        return False


def search_by_tag(target_tags_string_param: str) -> WebDriver:
    while True:  # 如果遇到搜索过载，继续尝试
        try:
            # 搜索是否成功？
            current_search_result.get(SEARCH_RESULT_URL_PREFIX + target_tags_string_param)
            error_message = current_search_result.find_element(By.XPATH, '//*[@id="post-list"]/div[2]/div/h1')
            # 搜索没有结果直接报错
            if "Nothing found" in error_message.text:
                print("搜索失败，没有结果！")
                exit(1)
            print("搜索目前过载！正在重试...")
            time.sleep(1)
            continue
        except NoSuchElementException:  # 如果没有对应元素反而是搜索成功
            print("搜索TAG:" + target_tags_string_param + " 成功！")
            return current_search_result


lock = threading.Lock()
successful_download_count = 0


def download_image_by_id(target_post_id_param: str, page_number=0):
    # 获取目标图片的唯一ID,合成目标post的详情页并打开
    target_post_vwr = webdriver.Chrome(options=option)
    # print("正在下载:" + "Page=" + str(page_number) + " 图片id=" + target_post_id_param)
    target_post_vwr_url = POST_VWR_URL_PREFIX + target_post_id_param
    target_post_vwr.get(target_post_vwr_url)

    # 在图片详情页面找到图片源地址
    target_post_url = target_post_vwr.find_element(By.LINK_TEXT, "Original image").get_attribute("href")
    # print("\t原图链接获取完成，准备下载...")
    response = requests.get(target_post_url)

    # 正式开始下载
    # 先得到下载的图片的文件名和路径
    save_file_name = SAVE_DIRECTORY + "\\" + target_post_id_param + ".jpg"
    # 检查原图url是否访问成功
    if response.status_code == 200:  # 成功
        with open(save_file_name, "wb") as file:
            file.write(response.content)
            # print("Page=" + str(page_number) + " 图片id=" + target_post_id_param + "保存成功！")
            download_status = True
            # 由于每个图片都是唯一的，不需要新增本次下载的图片，所以下面这行代码是多余的
            # existImgNames.append(targetPostImageId + ".jpg")
    else:
        print("图片获取失败！")
        download_status = False
    #  及时关闭无用标签页
    response.close()
    target_post_vwr.close()
    target_post_vwr.quit()

    # 成功下载的计数器在完成下载后自增
    global successful_download_count, lock
    lock.acquire()
    try:
        if download_status:
            successful_download_count += 1
    finally:
        lock.release()


def get_next_page(current_page: WebDriver, current_page_index_param: int):
    # print("正在切换到下一页，下一页的页码：" + str(current_page_index_param + 2))
    # 试图切换下一页时是否有误？
    while True:
        try:
            current_page.find_element(By.XPATH, "//a[@alt='next']").click()
            break
        except NoSuchElementException:
            # print("尝试点击下一页按钮时搜索过载！正在重试...")
            time.sleep(2)
            current_page.refresh()  # 刷新
            continue

    # 切换下一页后是否过载？
    while True:

        current_page.find_elements(By.CLASS_NAME, "thumb")

        if not current_page.find_elements(By.CLASS_NAME, "thumb"):
            # print("切换下一页后搜索过载，返回为空！正在重试...")
            time.sleep(2)
            current_page.refresh()
            continue
        break


#
# 主函数入口
#
print("保存目录为：" + SAVE_DIRECTORY_PREFIX)

# 创建一个webdriver对象，可以用这个对象的方法操纵网页
# 这个对象是当前搜索结果页面
current_search_result = webdriver.Chrome(options=option)  # C要大写，因为是类名

print("请输入你需要搜索的tag，用回车分隔，两次回车停止输入")
target_tags_list = []
while True:
    inputTag = input()
    if len(inputTag) == 0:
        break
    target_tags_list.append(inputTag)

# 处理Tags
target_tags_string = ""  # 形如xxxx+xxx_xxx的字符串
for tag in target_tags_list:
    target_tags_string += tag + "+"
target_tags_string = target_tags_string[:-1]  # 删掉最后一个加号

# 图片保存到对应文件夹
SAVE_DIRECTORY = SAVE_DIRECTORY_PREFIX + target_tags_string

# 搜索这个tag,搜索不到会报错退出
current_search_result = search_by_tag(target_tags_string)

# FIX:先搜索，有结果再决定是否创建新文件夹并检查存在的图片
if not os.path.exists(SAVE_DIRECTORY):  # 如果不存在就创建
    os.makedirs(SAVE_DIRECTORY)

# 哈希查找初始化
exist_img_names: list = os.listdir(SAVE_DIRECTORY)
exist_image_name_hash_table = {}
for exit_image_name in exist_img_names:
    exist_image_name_hash_table[exit_image_name[:-4]] = True

# 获取最大页数,如果没有对应元素就只有一页
MAX_PAGE = 0
try:
    last_page_url = (current_search_result
                     .find_element(By.XPATH, "//a[@alt='last page']")
                     .get_attribute("href"))
    last_page = webdriver.Chrome(options=option)

    # 可能遇到搜索过载需要重新搜索
    while True:
        last_page.get(last_page_url)
        print("\t尝试打开最后一页...")
        try:
            # 是否出现 Search currently overload提醒
            last_page.find_element(By.XPATH, '//*[@id="post-list"]/div[2]/div/h1')
            print("搜索目前过载！正在重试...")
            time.sleep(1)
            continue
        except NoSuchElementException:  # 搜索成功的时候反而没有提醒
            MAX_PAGE = int(last_page.find_element(By.XPATH, " //div[@class='pagination']//b").text)
            last_page.close()
            last_page.quit()
            break

    print("\t打开最后一页成功！")
except NoSuchElementException:  # 没有对应元素的时候
    MAX_PAGE = 1
print("一共有" + str(MAX_PAGE) + "页内容")

target_post_id_pool = []  # 初始化

# 开始获取所有待下载的图片
count = 0  # 总共下载多少图片
for current_page_index in tqdm(range(MAX_PAGE), leave=True, desc="已获取页数",
                               unit="页"):

    current_page_target_id_pool = []
    # print("\n***开始获取第" + str(current_page_index + 1) + "页内容...***")
    target_thumbs = current_search_result.find_elements(By.CLASS_NAME, "thumb")

    # 读取这一页上每个thumb的ID
    for target_thumb in target_thumbs:
        # 获取目标元素缩略图元素所含的图片的ID，去掉第一位的字母
        target_post_id = target_thumb.get_attribute("id")[1:]
        # 如果发现图片重复直接下载下一张
        if is_duplicate(target_post_id, exist_image_name_hash_table):
            # print(
            #     "Page=" + str(current_page_index + 1) + " 图片id:" + target_post_id + "已存在")
            continue
        current_page_target_id_pool.append(target_post_id)

    # print("第" + str(current_page_index + 1) + "页上未下载的的帖子ID：", current_page_target_id_pool)
    target_post_id_pool.extend(current_page_target_id_pool)  # 存入全部待下载的ID池

    # 切换到下一页
    if current_page_index < MAX_PAGE - 1:  # 最后一页的时候不需要切换
        get_next_page(current_page=current_search_result,
                      current_page_index_param=current_page_index)
    target_thumbs.clear()

# 开始多线程下载所有的图片
downloading_thread_pool = []

MAX_THREAD_COUNT = len(target_post_id_pool)
current_page_index = 0
for target_post_id in tqdm(target_post_id_pool, leave=True, desc="已创建下载",
                           unit="张"):  # 对列表进行遍历
    new_downloading_thread = threading.Thread(target=download_image_by_id,
                                              args=(target_post_id, current_page_index + 1))
    new_downloading_thread.start()
    downloading_thread_pool.append(new_downloading_thread)
    time.sleep(0.5)  # 防止爬虫过快
    current_page_index += 1  # 下载完一页之后列表+1

# 等待所有下载完成
for current_downloading_thread in tqdm(downloading_thread_pool, leave=True, desc="已完成总下载",
                                       unit="张"):  # tqdm:进度条
    current_downloading_thread.join()
print("图片全部下载完成！总共下载了" + str(successful_download_count) + "张图片")
current_search_result.close()
current_search_result.quit()
