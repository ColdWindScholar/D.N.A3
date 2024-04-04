import re
import requests

from bs4 import BeautifulSoup


def get_rom_link(model_version_link, today):
    miui_rom_link = 'https://bigota.d.miui.com/'
    response = requests.get(model_version_link)
    if not response.status_code == 200:
        raise RuntimeError(model_version_link + ' 请求异常！')
    soup = BeautifulSoup(response.content, 'html.parser')
    try:
        rom_div = soup.find_all(name='div', attrs={'class': 'content mb-5 rom-body'})[0].contents
    except IndexError:
        rom_div = soup.find_all(name='div', attrs={'class': 'content mb-5 featured-body'})[0].contents
    else:
        pattern = re.compile('<p>(.*?)<a(.*?)>下载</a></p>')
        rom_link_dic = {'recovery': {'stable': [], 'develop': []}, 'fastboot': {'stable': [], 'develop': []}}
        for tag in rom_div:
            rom_name = re.findall(pattern, str(tag))
            if not rom_name == []:
                rom_name = rom_name[0][0][:-3]
                if re.search('ota', rom_name):
                    pass
                else:
                    obj = re.search('(V\d+.*[A-Z]{7})|([A-Z]{3,7}\d{2}\\.\d)', rom_name)
                    if rom_name.split('.')[-1] == 'zip':
                        if obj:
                            rom_version = obj.group()
                            rom_link = miui_rom_link + rom_version + '/' + rom_name
                            rom_link_dic['recovery']['stable'].append(rom_link)
                        else:
                            if re.search(today, rom_name):
                                rom_version = rom_name.split('_')[2]
                                rom_link = miui_rom_link + rom_version + '/' + rom_name
                                rom_link_dic['recovery']['develop'].append(rom_link)
                    else:
                        if rom_name.split('.')[-1] == 'tgz':
                            if obj:
                                rom_version = obj.group()
                                rom_link = miui_rom_link + rom_version + '/' + rom_name
                                rom_link_dic['fastboot']['stable'].append(rom_link)
                            else:
                                rom_version = rom_name.rsplit('_', 5)[1]
                                if rom_version == 'images':
                                    rom_version = rom_name.split('_')[2]
                                    if rom_version == 'images':
                                        rom_version = rom_name.split('_')[3]
                                rom_link = miui_rom_link + rom_version + '/' + rom_name
                                rom_link_dic['fastboot']['develop'].append(rom_link)
        else:
            return rom_link_dic


def get_model_link_table():
    region_map = {'国行版': 'CN', '俄罗斯版 (俄版) (RU)': 'RU', '全球版': 'EN', '印度尼西亚版 (印尼版) (ID)': 'ID',
                  '印度版 (IN)': 'IN',
                  '欧洲版 (欧版) (EEA)': 'EU', '土耳其版 (TR)': 'TR', '台湾版 (台版) (TW)': 'TW',
                  '日本版 (日版) (JP)': 'JP', '新加坡版': 'SG'}
    link = 'https://xiaomirom.com/series/'
    response = requests.get(link)
    if not response.status_code == 200:
        raise RuntimeError(link + ' 请求异常！')
    soup = BeautifulSoup(response.content, 'html.parser')
    link_table = soup.find_all(name='dl', attrs={'class': 'row series__dl'})[0].contents
    model_link_table_dic = {}
    model_name_pattern = re.compile('[(](.*)[)]')
    for i in range(0, len(link_table), 2):
        model_name = re.findall(model_name_pattern, link_table[i].a.contents[0])[0]
        a_tags = link_table[i + 1].find_all(name='a')
        model_region_link_dic = {}
        for a in a_tags:
            region = a.contents[0]
            model_region_link_dic[region_map[region]] = a.attrs['href']
        else:
            model_link_table_dic[model_name] = model_region_link_dic

    else:
        return model_link_table_dic
