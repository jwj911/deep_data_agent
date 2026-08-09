import requests
from utils.tools import get_config
from utils.notify_roboy import NotifyRobot
import re


def get_tenant_access_token():
    # 设置应用的 App ID 和 App Secret
    app_id = get_config()['robot']['app_id']
    app_secret = get_config()['robot']['app_secret']
    data = requests.post(url='https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal/', data={
        'app_id': app_id,
        'app_secret': app_secret
    }).json()
    try:
        tenant_access_token = data['tenant_access_token']
    except Exception as e:
        logging.error(data)
    return tenant_access_token


def parser(content: str = ''):
    items = content.split('\n')
    items = re.split(r'</bold>|<bo', content)
    for item in items:
        if len(item) == 0:
            items.remove(item)
    result_temp = []
    result = []
    for item in items:
        result_temp.extend(item.split('color=blue>'))
    for item in result_temp:
        if len(item) == 0:
            continue
        if '<font' in item:
            _item = {
                "text_run": {
                    "content": item.replace('<font ', ''),
                    "text_element_style": {
                        # "background_color": 14,
                        "bold": True,
                        "text_color": 5
                    }
                },
            }
        else:
            _item = {
                "text_run": {
                    # "content": item if 'ld>' in item else item + '\n',
                    "content": item,
                    "text_element_style": {
                        "bold": False,
                    }
                }
            }
        if 'ld>' in item:
            _item['text_run']['text_element_style']['bold'] = True
            _item['text_run']['content'] = item.replace(
                'ld>', '').lstrip()
        result.append(_item)
    return result


def insert_financial_brief(content: dict = {}, document_id: str = ''):
    # 设置访问令牌
    access_token = get_tenant_access_token()
    content_insert = {
        "index": 0,
        "children": [
            {
                "block_type": 3,
                "heading1": {
                    "elements": [{
                        "text_run": {
                            "content": content['title']
                        }
                    }],
                    "style": {}
                },
            },
            {
                "block_type": 4,
                "heading2": {
                    "elements": [
                        {
                            "text_run": {
                                "content": "业绩表现概览"
                            }
                        }
                    ],
                    "style": {}
                },
            },
            {
                "block_type": 2,
                "text": {
                    "elements": parser(content['业绩表现概览'])
                },
                "style": {}
            },
            {
                "block_type": 4,
                "heading2": {
                    "elements": [
                        {
                            "text_run": {
                                "content": "下季度指引"
                            }
                        }
                    ],
                    "style": {}
                },
            },
            {
                "block_type": 2,
                "text": {
                    "elements": parser(content['下季度指引'])
                },
                "style": {}
            },
            {
                "block_type": 2,
                "text": {
                    "elements": [
                        {
                            "text_run": {
                                "content": "\n\n\n"
                            }
                        }
                    ],
                },
                "style": {}
            },
        ]
    }

    # 构建API请求的URL
    url = f'https://open.feishu.cn/open-apis/docx/v1/documents/{document_id}/blocks/{document_id}/children'

    # 设置请求头部
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    response = requests.post(url, headers=headers, json=content_insert)

    # 检查请求是否成功
    if response.status_code == 200:
        print('文本成功写入飞书文档！')
    else:
        print('写入文本时出现问题：', response.text)


def financial_brief_card(brief={}, groupnames=[]):
    nr = NotifyRobot()
    message = {
        "msg_type": "interactive",
        "card": {
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "content": '**业绩表现概览**',
                        "text_size": "heading-4",
                        "tag": "lark_md"
                    }
                },
                {
                    "tag": "div",
                    "text": {
                        "content": brief['业绩表现概览'].replace('<bold>', '**').replace('</bold>', '**').strip(),
                        "tag": "lark_md"
                    }
                },
                {
                    "tag": "div",
                    "text": {
                        "content": '**下季度指引**',
                        "tag": "lark_md",
                        "text_size": "heading-4",
                    }
                },
                {
                    "tag": "div",
                    "text": {
                        "content": brief['下季度指引'].replace('<bold>', '**').replace('</bold>', '**').strip(),
                        "tag": "lark_md"
                    }
                },
                {
                    "actions": [{
                        "tag": "button",
                        "text": {
                            "content": "本财报季摘要列表",
                            "tag": "lark_md"
                        },
                        "url": "https://sourcecodecap.feishu.cn/docx/FG64dUBM3oYioFxd3wXctQNInDP",
                        "type": "default",
                        "value": {}
                    }],
                    "tag": "action"
                }],
            "header": {
                "template": "yellow",
                "title": {
                    "content": f"{brief['title']}财报更新",
                    "tag": "plain_text"
                }
            }
        }
    }
    nr.notify_by_webhook(groupnames=groupnames, message=message, msg_type='card')
    # nr.notify_by_webhook(groupnames=['先把财报智能工具跑起来~~'], message=message, msg_type='card')


if __name__ == "__main__":
    text = {'title': 'DUOL 2024Q1', '业绩表现概览': '\n<bold>总收入  </bold>usd167.55mn, (+44.82% yoy, +10.96% qoq).\n<bold>收入细项</bold>\nSubscription: $131,688\nAdvertising: $12,952\nDuolingo English Test: $12,755\nIn-App Purchases: $9,924\nOther: $234\n<bold>Gross profit  </bold>usd122.36mn(+45.32% yoy, +10.82% qoq), <bold>GM  </bold>+73.03%, (0.0 ppt yoy). None\n<bold>EBITDA  </bold>usd44.01mn, (+191.42% yoy，+25.03% qoq). <bold>EBIT margin  </bold>44.01mn(+191.42% yoy). None\n<bold>净利润  </bold>usd26.96mn (-1136.77% yoy, +122.46% qoq), <bold>NM  </bold>+16.09%(0.18 ppt yoy). Duolingo的净收入增长主要是由于强劲的预订和收入增长以及创纪录的盈利能力。\n', '下季度指引': '1. Duolingo 2024年第二季度截至3月31日的财务展望：\n    a. 总预订量：预计在$179.0 million ~ $181.5 million的范围内。\n    b. 收入：预计在$175.0 million ~ $177.5 million之间。\n    c. 调整后的EBITDA：预计在$36.8 million ~ $39.1 million之内。\n    d. 调整后的EBITDA利润率：预计在21% ~ 22%之间。\n\n2. Duolingo 2024年全年截至12月31日的财务展望：\n    a. 总预订量：预计在$808.5 million ~ $817.5 million的范围内。\n    b. 收入：预计在$726.5 million ~ $735.5 million之间。\n    c. 调整后的EBITDA：预计在$167.1 million ~ $176.5 million之间。\n    d. 调整后的EBITDA利润率：预计在23% ~ 24%之间。'}
    text_panw = {'title': 'PANW 2024Q3', '业绩表现概览': '\n<bold>总收入  </bold>usd1.98bn, (+16.75% yoy, -0.76% qoq).\n<bold>收入细项</bold>\nProduct: $391.0 million\nSubscription and support: $1,593.8 million\n<bold>Gross profit  </bold>usd1.47bn(+18.06% yoy, -0.33% qoq), <bold>GM  </bold>+74.12%, (0.01 ppt yoy). None\n<bold>EBIT  </bold>usd507.9mn, (None yoy，None qoq). <bold>EBIT margin  </bold>507.9mn(None yoy). None\n<bold>净利润  </bold>usd454.9mn (+321.99% yoy, -9.02% qoq), <bold>NM  </bold>+22.92%(0.17 ppt yoy). 净利润的增长主要是由于公司在执行中保持了纪律性，同时在市场推广和创新方面进行了投资。\n', '下季度指引': '1. 2024财年第四季度展望：\n    a. 总账单：$3.43 billion ~ $3.48 billion\n    b. 总收入：$2.15 billion ~ $2.17 billion\n    c. 每股稀释非GAAP净收益：$1.40 ~ $1.42\n\n2. 2024财年展望：\n    a. 总账单：$10.13 billion ~ $10.18 billion\n    b. 总收入：$7.99 billion ~ $8.01 billion\n    c. 非GAAP运营利润率：26.8% ~ 27.0%\n    d. 每股稀释非GAAP净收益：$5.56 ~ $5.58\n    e. 调整后自由现金流利润率：38.5% ~ 39.0%'}
    text_amer = {'title': 'AMER 2024Q1', '业绩表现概览': '\n<bold>总收入  </bold>usd1.18bn, (None yoy, -10.05% qoq).\n<bold>收入细项</bold>\nTechnical Apparel: $510 million\nOutdoor Performance: $400 million\nBall & Racquet Sports: $273 million\n<bold>Gross profit  </bold>usd638.5mn(None yoy, -6.52% qoq), <bold>GM  </bold>+53.98%, (None ppt yoy). 毛利率的提高主要是由于向技术服装这一最高毛利率部门的收入组合转移，以及物流成本的降低，部分被原材料成本的上升和与去年相比更高的产品折扣所抵消。\n<bold>EBIT  </bold>usd109mn, (None yoy，-20.44% qoq). <bold>EBIT margin  </bold>109mn(None yoy). 调整后的营业利润的下降主要是由于销售增长放缓导致的销售和管理费用占收入的比例增加。\n<bold>净利润  </bold>usd6.9mn (None yoy, -107.27% qoq), <bold>NM  </bold>+0.58%(None ppt yoy). 净收入的变化主要是由于销售和管理费用的增加，以及净融资成本的增加。\n', '下季度指引': '1. 2024年全年Amer Sports财务预测\n    a. 报告的收入增长：中等青少年%\n    b. 毛利率：约54.0%\n    c. 营业利润率：10.5% ~ 11.0%\n    d. 净财务成本：$215 million ~ $225 million\n    e. 有效税率：约38%\n    f. 全摊薄EPS：接近先前指导范围的高端，即$0.30至$0.40\n\n2. 2024年第二季度Amer Sports财务预测\n    a. 收入增长：约10%\n    b. 毛利率：约54.0%\n    c. 营业利润率：约0.0%\n    d. 净财务成本：$45 million ~ $50 million\n    e. 有效税率：约38%\n    f. 全摊薄EPS：$(0.04)至$(0.08)\n\n这种格式清晰、有条理地展示了财务预测，使读者更容易理解Amer Sports在2024年全年和第二季度的预期财务表现。'}
    text_nvda = {'title': 'NVDA 2025Q1', '业绩表现概览': '\n<bold>总收入  </bold>usd26.04bn, (+262.12% yoy, +17.83% qoq).\n<bold>收入细项</bold>\nCompute & Networking: $22,675 million\nGraphics: $3,369 million\nData Center: $22,563 million\nCompute: $19,392 million\nNetworking: $3,171 million\nGaming: $2,647 million\nProfessional Visualization: $427 million\nAutomotive: $329 million\nOEM and Other: $78 million\n<bold>Gross profit  </bold>usd20.56bn(+328.15% yoy, +21.23% qoq), <bold>GM  </bold>+78.94%, (0.12 ppt yoy). 毛利率的提高主要是由于数据中心收入的强劲增长，这主要得益于我们的Hopper GPU计算平台，以及由于较低的库存费用所带来的好处。\n<bold>EBIT  </bold>usdNone, (None yoy，None qoq). <bold>EBIT margin  </bold>None(None yoy). None\n<bold>净利润  </bold>usd15.24bn (+461.67% yoy, +18.69% qoq), <bold>NM  </bold>+58.51%(0.21 ppt yoy). 净收入的增长主要是由于收入的增长。\n', '下季度指引': '1. 收入预期：\n    a. 预计收入将约为$28.0 billion，可能的变动范围为正负2%。\n\n2. 毛利率预测：\n    a. 预计GAAP和non-GAAP的毛利率分别为74.8%和75.5%，可能的变动范围为正负50个基点。\n    b. 预计全年的毛利率将在70%的中等范围内。\n\n3. 营业费用预测：\n    a. 预计GAAP和non-GAAP的营业费用将分别约为$4.0 billion和$2.8 billion。\n    b. 预计全年的营业费用将在40%的低端范围内增长。\n\n4. 其他收入和费用预测：\n    a. 预计GAAP和non-GAAP的其他收入和费用将产生约$300 million的收入，不包括来自非关联投资的任何收益和损失。\n\n5. 税率预测：\n    a. 预计GAAP和non-GAAP的税率将为17%，可能的变动范围为正负1%，不包括任何离散项目。'}
    text_pdd = {'title': 'PDD 2024Q1', '业绩表现概览': '\n<bold>总收入  </bold>rmb86.81bn, (+130.66% yoy, -2.33% qoq).\n<bold>收入细项</bold>\nOnline marketing services and others: RMB42,456.2 million (US$5,880.1 million)\nTransaction services: RMB44,355.8 million (US$6,143.2 million)\n<bold>Gross profit  </bold>rmb54.12bn(+104.13% yoy, +0.58% qoq), <bold>GM  </bold>+62.34%, (-0.08 ppt yoy). None\n<bold>EBIT  </bold>rmb25.97bn, (+274.85% yoy，+15.98% qoq). <bold>EBIT margin  </bold>+29.92%(0.12 ppt yoy). 营业利润的增长主要是由于营业收入的增长。\n<bold>净利润  </bold>rmb28bn (+245.61% yoy, +20.26% qoq), <bold>NM  </bold>+32.25%(0.11 ppt yoy). 净利润的增长主要是由于营业收入的增长。\n', '下季度指引': 'PDD控股2024年第一季度的财务报告并未提供对未来几个季度或年度的具体展望。'}
    text_beke = {'title': '贝壳 2024Q1', '业绩表现概览': '\n<bold>总收入  </bold>rmb16.4bn, (-19.21% yoy, -99.92% qoq).\n<bold>收入细项</bold>\nExisting home transaction services: RMB 5.7 billion\nNew home transaction services: RMB 4.9 billion\nHome renovation and furnishing: RMB 2.4 billion\nHome rental services: RMB 2.6 billion\nEmerging and other services: RMB 0.7 billion\n<bold>Gross profit  </bold>rmb4.1bn(-34.92% yoy, -99.92% qoq), <bold>GM  </bold>+25.0%, (-0.06 ppt yoy). 毛利率的下降主要是由于房屋租赁服务的净收入占比增加但贡献利润率相对较低，以及现有房屋交易服务和新房交易服务的贡献利润率下降。\n<bold>EBIT  </bold>rmb1.67bn, (-44.06% yoy，-2.0% qoq). <bold>EBIT margin  </bold>+10.16%(-0.05 ppt yoy). 调整后的营业收入和调整后的EBITDA均有所下降，主要是由于总收入的减少和运营费用的增加。\n<bold>净利润  </bold>rmb432mn (-84.29% yoy, -99.94% qoq), <bold>NM  </bold>+2.63%(-0.11 ppt yoy). 净利润的减少主要是由于总收入的减少和运营费用的增加。\n', '下季度指引': '贝壳控股有限公司2024年第一季度的财务报告并未提供对未来的具体展望。'}
    text_msft = {'title': 'MSFT 2024Q3', '业绩表现概览': '\n<bold>总收入  </bold>usd61.9bn, (+17.01% yoy, -0.19% qoq).\n<bold>收入细项</bold>\nProductivity and Business Processes: $19.6 billion 12%\nIntelligent Cloud: $26.7 billion 21%\nMore Personal Computing: $15.6 billion 17%\n<bold>Gross profit  </bold>usd43.35bn(+18.03% yoy, +2.25% qoq), <bold>GM  </bold>+70.04%, (0.01 ppt yoy). \n<bold>EBIT  </bold>usd27.58bn, (None yoy，None qoq). <bold>EBIT margin  </bold>+44.56%(None yoy). \n<bold>净利润  </bold>usd21.94bn (+19.89% yoy, +0.32% qoq), <bold>NM  </bold>+35.44%(0.01 ppt yoy). 净收入的增长主要是由于Microsoft Cloud的强劲表现，以及销售团队和合作伙伴的出色执行。\n', '下季度指引': '1. 微软2024年第三季度的财务报告并未提供具体的未来展望。\n2. 该公司提到，它将在其盈利电话会议和网络广播中提供前瞻性指导。'}
    text_amazon = {'title': 'AMAZON 2024Q1', '业绩表现概览': '\n<bold>总收入  </bold>usd143.3bn, (+12.52% yoy, -15.69% qoq).\n<bold>收入细项</bold>\nOnline stores: $54.67 billion 7%\nPhysical stores: $5.20 billion 6%\nThird-party seller services: $34.60 billion 16%\nAdvertising services: $11.82 billion 24%\nSubscription services: $10.72 billion 11%\nAWS: $25.04 billion 17%\n<bold>Gross profit  </bold>usd143.3bn(+140.57% yoy, +85.12% qoq), <bold>GM  </bold>+100.0%, (0.53 ppt yoy). None\n<bold>EBIT  </bold>usd15.31bn, (None yoy，+15.88% qoq). <bold>EBIT margin  </bold>+10.68%(None yoy). EBIT的增长主要是由于运营收入的增加，从2023年第一季度的48亿美元增加到2024年第一季度的153亿美元。\n<bold>净利润  </bold>usd10.4bn (+227.87% yoy, -2.11% qoq), <bold>NM  </bold>+7.26%(0.05 ppt yoy). 净收入的增长主要是由于运营收入的增加，从2023年第一季度的48亿美元增加到2024年第一季度的153亿美元。\n', '下季度指引': '1. 2024年第二季度净销售预测\n    a. 亚马逊预计净销售额将在$144.0 billion和$149.0 billion之间。\n    b. 与2023年第二季度相比，这代表了7%到11%的增长。\n\n2. 外汇汇率的影响\n    a. 预测考虑到了外汇汇率大约60个基点的不利影响。\n\n3. 2024年第二季度的营业收入\n    a. 预计营业收入将在$10.0 billion和$14.0 billion之间。\n    b. 与2023年第二季度的$7.7 billion相比。\n\n4. 预测的假设\n    a. 该指导预测假设没有额外的业务收购，重组或法律结算。'}
    text_alphabet = {'title': 'ALPHABET 2024Q1', '业绩表现概览': '\n<bold>总收入  </bold>usd80.54bn, (+15.41% yoy, -6.69% qoq).\n<bold>收入细项</bold>\nGoogle Search & other: $46,156 million up 14% year-on-year\nYouTube ads: $8,090 million up 21% year-on-year\nGoogle Network: $7,413 million down 1% year-on-year\nGoogle advertising: $61,659 million up 13% year-on-year\nGoogle subscriptions, platforms, and devices: $8,739 million up 18% year-on-year\nGoogle Services total: $70,398 million up 14% year-on-year\nGoogle Cloud: $9,574 million up 28% year-on-year\nOther Bets: $495 million up 72% year-on-year\n<bold>Gross profit  </bold>usd46.83bn(+55.18% yoy, -3.92% qoq), <bold>GM  </bold>+58.14%, (0.15 ppt yoy). None\n<bold>EBIT  </bold>usdNone, (None yoy，None qoq). <bold>EBIT margin  </bold>None(None yoy). EBIT的变化主要是由于公司整体的收入增长以及持续努力在持久地重构成本基础上取得的成果。\n<bold>净利润  </bold>usd23.66bn (+57.21% yoy, +14.38% qoq), <bold>NM  </bold>+29.38%(0.08 ppt yoy). 净收入的变化主要是由于公司整体的收入增长以及持续努力在持久地重构成本基础上取得的成果。\n', '下季度指引': 'Alphabet的2024Q1财务报告并未提供对未来的具体展望。'}
    # financial_brief_card(brief=text_nvda, groupnames=['财报摘要'])
    # financial_brief_card(brief=text_pdd, groupnames=['财报摘要'])
    
    financial_brief_card(brief=text_alphabet, groupnames=['先把财报智能工具跑起来~~'])
    financial_brief_card(brief=text_msft, groupnames=['先把财报智能工具跑起来~~'])
    financial_brief_card(brief=text_amazon, groupnames=['先把财报智能工具跑起来~~'])
    # financial_brief_card(brief=text, groupnames=['财报摘要'])
    # context2doc()
