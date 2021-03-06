# coding: utf-8
# author: Why
# version: 5.0.2
import argparse
import os
import sys
import smtplib
import string
import time

from email import encoders
from email.header import Header
from email.mime.multipart import MIMEBase, MIMEMultipart
from email.mime.text import MIMEText

from collections.abc import Iterable
from ocrApi import img2str
import numpy as np
from PIL import Image
import pandas as pd
import prettytable

from config import *
from utils import *
from email_config import *
# from ipdb import set_trace

print('')

print('    ______            ____        __         ')
print('   / ____/___ _____  / __ \____  / /_  ____  ')
print('  / /_  / __ `/ __ \/ /_/ / __ \/ __ \/ __ \\')
print(' / __/ / /_/ / /_/ / _, _/ /_/ / /_/ / /_/ / ')
print('/_/    \__, /\____/_/ |_|\____/_.___/\____/  ')
print('      /____/                               \n')

SYSTEM = sys.platform

if SYSTEM == 'linux':
    print('-' * 30)
    print('➜ Current system: Linux')
    from utils_linux import *
else:
    from utils_win import *

# ===== Config: =====
Args = argparse.ArgumentParser()
Args.add_argument('--epoch', '-e', type=int, default=3,
                  help='Num of running battles.')

Args.add_argument('--support', '-s', type=str,
                  help='ID or name (e.g. `sab` for saber, program will AutoComplete the name) of support servent. ServentID: 0. all,  1. saber,  2. archer,  3. lancer,  4. rider,  5. caster,  6. assassin,  7. berserker,  8. special')

Args.add_argument('--skill', '-S', type=str, default='+',
                  help='Skills you want to set. e.g: `S+12345` for only using 1~5, `S-123` for only NOT using skill 1~3, `S-` for not using any skill, `S+` for using all skills.')

Args.add_argument('--config_file', '-cf', type=str,
                  help='csv formated config file for skills, ult and atk order.')

Args.add_argument('--ultimate', '-u', type=str, default='123',
                  help='Ultimate Skills you want to use. exmaple: `u12` for using 1~2, `u-` for NOT using anyone.')

Args.add_argument('--order', '-o', type=int, choices=range(-3, 4), default=0,
                  help='Attacking orders. `n` for attacking `n`th enemy first; `-n` for attacking `n`th enemy first and others in reverse order; 0 for ignoring settings. 1, 2, 3 from RIGHT to LEFT.')

Args.add_argument('--keep', '-k', type=int,
                  help='if 0: keep the window-position same as the last time; if n: load from file n')

Args.add_argument('--clearAP', '-C', type=int, default=0,
                  help='If clear all AP. -Cn to represent: One apple can run n battles. for example, full AP = 125, AP cost by one battle = 40, then n = 3. set 0 for not clearing AP.')

Args.add_argument('--OCR', '-O', action='store_true',
                  help='Use OCR to help attacking. I recommend you use it in some difficult battles.')

Args.add_argument('--no_focus', '-nf', action='store_true',
                  help='Don\'t make cursor focus on Fgo window. You should turn this on when you want to do other things while running fgo.')

Args.add_argument('--CheckPos', '-p', action='store_true',
                  help='To see the window-position, shoud be used with `--keep`.')
Args.add_argument('--debug', '-d', action='store_true',
                  help='Enter DEBUG mode.')
Args.add_argument('--shutdown', '-sd', action='store_true',
                  help='close the simulator after running.')
Args.add_argument('--ContinueRun', '-c', action='store_true',
                  help='Continue running in a battle.')
Args.add_argument('--locate', '-l', action='store_true',
                  help='Monitor cursor\'s  position.')
opt = Args.parse_args()

# ===== Global verible: =====
END_AFTER_THIS_EPOCH = False
PRE_BREAK_TIME = CLICK_BREAK_TIME
KEEP_POSITION = opt.keep if opt.keep != None else False
SEND_MAIL = False if opt.epoch < 5 or opt.debug else True
CURRENT = {
    'epoch': 0,
    'scene': 1,
    'turn': 1
}

# ===== Main Code: =====


def update_var():
    if opt.shutdown and SYSTEM == 'linux':
        input(
            '\033[1;31m➜ [Warning] Your PC will shutdown after running. Continue?\033[0m')
    if opt.debug:
        print('➜ [Attention] You are in DEBUG Mode!')

    # Parse opt.skill and opt.ultimate:
    if opt.skill:
        if opt.skill[0] in ('+', '-'):
            for x in opt.skill[1:]:
                if x not in '123456789':
                    print('[Error] `Skill` args format error, try again.')
                    os._exit(0)
            if opt.skill[1:] == '':
                opt.skill = tuple(range(1, 10)) if opt.skill[0] == '+' else ()
            elif opt.skill[0] == '+':
                opt.skill = tuple([int(x) for x in opt.skill[1:]])
            else:
                opt.skill = tuple({x for x in range(1, 10)} -
                                  set([int(x) for x in opt.skill[1:]]))
        else:
            print('[Error] Args <skill> format error, try again.')
            os._exit(0)
    if opt.ultimate:
        if opt.ultimate == '-':
            opt.ultimate = ()
        else:
            for x in opt.ultimate:
                if x not in '123':
                    print('[Error] Args <ultimate> format error, try again.')
                    os._exit(0)
            opt.ultimate = tuple([int(x) for x in opt.ultimate])

    # use default support servant:
    if not opt.support:
        return

    # Parse opt.support:
    try:
        opt.support = int(opt.support)
        if opt.support not in tuple(range(9)):
            print('[Error] Args <Support> format error, try again.')
            os._exit(0)
    except:
        supportID = ('all', 'saber', 'archer', 'lancer', 'rider',
                     'caster', 'assassin', 'berserker', 'special')

        res = [opt.support in x for x in supportID]
        if res.count(True) != 1:
            print('[Error] Args <Support> format error, try again.')
            os._exit(0)
        else:
            opt.support = res.index(True)


def info(str):
    logging.info('<E{}/{}> - {}'.format(CURRENT['epoch'], opt.epoch, str))


class DigitFinder:
    def __init__(self, keep=string.digits):
        self.comp = dict((ord(c), c) for c in keep)

    def __getitem__(self, k):
        return self.comp.get(k)


class Fgo:
    '''
    Important Info:
    ------------
    * 1 battle = 3 scenes (or less) = n turns
    * ajust SCALE in utils_linux/win.py if you changed the screen scale.
    '''
    __slots__ = ('c', 'width', 'height', 'scr_pos1',
                 'scr_pos2', 'area', 'img', 'LoadImg', 'skill_used_turn', 'digitFinder', 'kb_listener', 'config')

    def __init__(self, full_screen=True, sleep=True):
        # [init by yourself] put cursor at the down-right position of the game window.
        self.c = Cursor(init_pos=False)
        self.digitFinder = DigitFinder()
        if full_screen:
            self.width, self.height = self.c.get_screen_wh()
            self.scr_pos1 = (0, 0)
            self.scr_pos2 = (self.width, self.height)
            for x in range(5):
                logging.info(
                    'Start in %d s, Please enter FULL SCREEN.' % (5 - x))
                time.sleep(1)
        else:
            if type(KEEP_POSITION) == int or opt.CheckPos:
                with open(ROOT + 'data/INIT_POS.{}'.format(KEEP_POSITION), 'r') as f:
                    res = f.readlines()
                res = tuple([int(x) for x in res[0].split(' ')])
                self.scr_pos1 = res[:2]
                self.scr_pos2 = res[2:]
                if opt.CheckPos:
                    self.c.move_to(self.scr_pos1)
                    time.sleep(0.5)
                    self.c.move_to(self.scr_pos2)
                    os._exit(0)
                if KEEP_POSITION == 0:
                    print('➜ Running keeping last position.')
                elif KEEP_POSITION:
                    print('➜ Load init_pos from file', KEEP_POSITION)
            else:
                while 1:
                    if input('➜ Move cursor to <top-left>, then press ENTER (q to exit): ') == 'q':
                        print('➜ Running stop')
                        os._exit(0)
                    self.scr_pos1 = self.c.get_pos()
                    print('➜ Get cursor at {}'.format(self.scr_pos1))

                    if input('➜ Move cursor to <down-right>, then press ENTER (q to exit): ') == 'q':
                        print('➜ Running stop')
                        os._exit(0)
                    self.scr_pos2 = self.c.get_pos()
                    print('➜ Get cursor at {}'.format(self.scr_pos2))

                    res = input('Continue? [y(continue) /n(reset) /q(quit)]:')
                    if res == 'n':
                        continue
                    elif res == 'q':
                        os._exit(0)
                    else:
                        break
                if sleep:
                    for x in range(3):
                        logging.info(
                            'Start in %d s, make sure the window not covered.' % (3 - x))
                        time.sleep(1)
                with open(ROOT + 'data/INIT_POS.0', 'w') as f:
                    pos = str(self.scr_pos1[0]) + ' ' + str(self.scr_pos1[1]) + \
                        ' ' + str(self.scr_pos2[0]) + \
                        ' ' + str(self.scr_pos2[1])
                    f.write(pos)
                    print('➜ Position info saved.')
            self.width = abs(self.scr_pos2[0] - self.scr_pos1[0])
            self.height = abs(self.scr_pos2[1] - self.scr_pos1[1])
            print('-' * 30)

        # ===== position info: =====
        self.area = {
            'menu': (0.0693, 0.7889, 0.1297, 0.8917),  # avator position
            'StartMission': (0.8984, 0.9352, 0.9542, 0.9630),
            'AP_recover': (0.2511, 0.177, 0.2907, 0.2464),
            # 'support': (0.6257, 0.1558, 0.6803, 0.1997),
            'atk': (0.8708, 0.7556, 0.8979, 0.8009),
            # 'atk': (0.9155, 0.252, 0.9527, 0.328),
            'fufu': (0.9, 0.85, 1.0, 1.0),
            'normal-scene': (0.3446, 0.3908, 0.6622, 0.5451),
            'final-scene': (0.3446, 0.3908, 0.6622, 0.5451),
            # '下一步' button
            'BattleFinish': (0.8223, 0.9089, 0.9126, 0.9606)
        }
        self.img = {x: None for x in self.area.keys()}

        # images of skills in used state (drak):
        self.img['onCD-skills'] = [None] * 9
        # image of skills which can be used (light):
        # self.img['active-skills'] = list(range(9))

        # load sample imgs:
        try:
            self.LoadImg = {x: Image.open(
                ROOT + 'data/samples/{}.png'.format(x)) for x in self.area.keys()}
        except Exception:
            print('[Warning] Some sample images not found.')
        if not opt.ContinueRun and not opt.debug and not opt.locate:
            if self._monitor('menu', 3, 0) == -1:
                os._exit(0)

        '''
        Config File Example (*.conf):
        --------
        scene, allowed-skills, ultimate, atk-order
        1, none, none, 1
        2, 123456789, none, -2
        3, 123456789, 123, -3
        
        * none for not using skills; 
        * atk-order format is the same as args `--order`.
        '''
        if opt.config_file:
            '''
            self.config Format:
            ------------------
            {
             'allowed-skills':  {'1': '123456789',  '2': '123456789',   '3': '123456789'},
             'atk-order':       {'1': '1',          '2': '1',           '3': '1'},
             'ultimate':        {'1': 'none',       '2': 'none',        '3': '123'}
            }
            '''
            self.config = pd.read_csv(
                opt.config_file, sep=', ', dtype=str, engine='python').set_index('scene').to_dict()
            print(prettytable.from_csv(open(opt.config_file, 'r')))

        if SYSTEM == 'linux':
            self.kb_listener = KeyEventListener()
            self.kb_listener.start()

    def grab(self, float_pos, fname=None, to_PIL=False):
        '''
        Args:
        ------
        * float_pos: position tuple of target area, should be floats from 0~1, or name in `self.area`
        * fname=None: file name to save.
        * to_PIL=False: Only set `True` when: on linux using `autopy` and need a PIL jpg image.
        '''
        if type(float_pos) == str:
            float_pos = self.area[float_pos]

        float_x1, float_y1, float_x2, float_y2 = float_pos
        # 开了屏幕缩放的话，记得传参scale！
        x1, y1 = self._set(float_x1, float_y1, scale=SCALE)
        x2, y2 = self._set(float_x2, float_y2, scale=SCALE)
        return ScreenShot(x1, y1, x2, y2, to_PIL=to_PIL, fname=fname)

    def monitor_cursor_pos(self):
        while 1:
            x, y = self.c.get_pos()
            if self.scr_pos2[0] > x > self.scr_pos1[0] and self.scr_pos2[1] > y > self.scr_pos1[1]:
                x = (x - self.scr_pos1[0]) / self.width
                y = (y - self.scr_pos1[1]) / self.height
                pos = (round(x, 4), round(y, 4))
            else:
                pos = 'Not in Fgo.'
            info('Float pos: {}, real: {}'.format(pos, self.c.get_pos()))
            time.sleep(0.5)

    def _set(self, float_x, float_y, scale=False):
        '''
        * float_x, float_y: float position on the WINDOW.
        * scale: scale factor, type: int, >1
        * return the real position on the screen.
        '''
        x = int(self.scr_pos1[0] + self.width * float_x)
        y = int(self.scr_pos1[1] + self.height * float_y)
        if scale:
            x = int(x / scale)
            y = int(y / scale)
        return x, y

    def click(self, float_x, float_y, sleep_time):
        x, y = self._set(float_x, float_y, scale=False)
        bak_x, bak_y = self.c.get_pos()

        # add noise to (x, y):
        x += np.random.randint(0, 4)
        y += np.random.randint(0, 4)

        self.c.click((x, y))
        if opt.no_focus:
            # click the original position to make cursor focus on your jobs:
            self.c.click((bak_x, bak_y))
        else:
            # just move back:
            self.c.move_to((bak_x, bak_y))

        sleep_time *= (np.random.rand() * 0.1 + 1)
        time.sleep(sleep_time)

    def send_mail(self, status):
        # status: 'err' or 'done'
        self.grab((0, 0, 1, 1), 'final_shot')
        with open(ROOT + 'data/fgo.LOG', 'r') as f:
            res = f.readlines()
            res = [x.replace('<', '&lt;').replace('>', '&gt;') for x in res]
            res = ''.join([x[:-1] + '<br />' for x in res])
        msg = MIMEMultipart()
        with open(ROOT + 'data/final_shot.png', 'rb') as f:
            mime = MIMEBase('image', 'jpg', filename='shot.png')
            mime.add_header('Content-Disposition',
                            'attachment', filename='shot.png')
            mime.add_header('Content-ID', '<0>')
            mime.add_header('X-Attachment-Id', '0')
            mime.set_payload(f.read())
            encoders.encode_base64(mime)
            msg.attach(mime)

        msg.attach(MIMEText('<html><body><p><img src="cid:0"></p>' +
                            '<font size=\"1\">{}</font>'.format(res) +
                            '</body></html>', 'html', 'utf-8'))
        msg['From'] = Header('why酱のFGO脚本', 'utf-8')
        msg['Subject'] = Header(
            '[FGO] - Status: {}, {}'.format(status, time.strftime('%m-%d%H:%M')), 'utf-8')
        server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT)
        try:
            server.ehlo()
            # server.starttls()
            server.login(FROM_ADDRESS, PASSWD)
            server.sendmail(FROM_ADDRESS, [TO_ADDRESS], msg.as_string())
            server.quit()
            print('➜ Mail sent successfully. Please check it.')
        except Exception as e:
            print('\nError type: ', e)
            print('➜ Mail sent failed. Maybe there are something wrong.')

    def _mission_start(self):
        # postion of `mission start` tag
        for _ in range(3):
            self.click(0.9398, 0.9281, 1)
        if CHOOSE_ITEM:
            # using the first item:
            # self.click(0.5, 0.2866, 0.5)
            # self.click(0.6478, 0.7819, 0.5)

            # not using item:
            self.click(0.6469, 0.9131, 0.5)

    def enter_battle(self, supNo):
        # [init by yourself] put the tag of battle at the top of screen.
        # postion of support servant tag.
        sup_tag_x = 0.4893
        sup_tag_y = 0.3944
        # click to hide the terminal:
        # if CURRENT['epoch'] == 1:
        #     self.click(0.2828, 0.7435, 0.3)

        # click the center of battle tag.
        # self.click(0.7252, 0.2740, 2)
        self.click(0.7252, 0.2740, 0)
        self.use_apple()
        # choose support servent class icon:
        # time.sleep(EXTRA_SLEEP_UNIT*4)

        if supNo:
            if CURRENT['epoch'] == 1:
                time.sleep(1.5)
            self.click(0.0729 + 0.0527 * supNo, 0.1796, 1)
        else:
            time.sleep(1)
        self.click(sup_tag_x, sup_tag_y, 1)

        # if self._monitor('StartMission', 10, 0.3) != -1:
        # no screenshot bugs, change to:
        if True:
            time.sleep(1)
            self._mission_start()
            return 0
        else:
            self.click(sup_tag_x, sup_tag_y, 1)
            if not (similar(self.grab(self.area['StartMission'], to_PIL=True)[0], self.img['StartMission'])):
                logging.error('Can\'t get START_MISSION tag for 10s.')
                self.send_mail('Error')
                raise RuntimeError('Can\'t get START_MISSION tag for 10s')

    def get_skill_imgs(self, allowed_skills, saveImg=False):
        # turn = False for update imgs of all 9 skills.
        ski_x = [0.0542, 0.1276, 0.2010, 0.3021,
                 0.3745, 0.4469, 0.5521, 0.6234, 0.6958]
        ski_y = 0.8009
        skill_imgs = [None] * 9
        for no in opt.skill:
            i = no - 1
            if allowed_skills and no not in allowed_skills:
                # just use the old img:
                skill_imgs[i] = self.img['onCD-skills'][i]
                continue
            # N = 25 if SYSTEM == 'linux' else 1
            # Screenshot bug (gray block bug) has been fixed. 1 is enough:
            N = 1
            imgs = [self.grab((ski_x[i] - 0.0138, ski_y - 0.0222,
                               ski_x[i] + 0.0138, ski_y)) for _ in range(N)]
            img = imgs[0]
            if N > 1:
                max_count = imgs.count(imgs[0])
                for x in imgs:
                    count = imgs.count(x)
                    if count > max_count:
                        img = x
                        max_count = count
            # skill_imgs[i] = self.grab(
            #     (ski_x[i]-0.0138, ski_y-0.0222, ski_x[i]+0.0138, ski_y))
            skill_imgs[i] = img
            if saveImg:
                skill_imgs[i].save('./debug/{}.png'.format(i))
        return skill_imgs

    def _use_one_skill(self, turn, skill_ix):
        ski_x = [0.0542, 0.1276, 0.2010, 0.3021,
                 0.3745, 0.4469, 0.5521, 0.6234, 0.6958]  # ski_y = 0.8009
        # if not (skill_ix == 7 and turn == 1):
        self.click(ski_x[skill_ix], 0.8009, SKILL_SLEEP1)
        self.click(0.5, 0.5, SKILL_SLEEP2)
        self.click(0.6978, 0.0267, SKILL_SLEEP3)
        # To see if skill is really used.
        beg = time.time()
        click_status = True
        while not (self.grab(self.area['atk']) == self.img['atk']):
            # to avoid clicking avator:
            if click_status and not int(time.time() - beg) % 0.5:
                # time.sleep(0.5)
                self.click(0.6978, 0.0267, 0)
                click_status = False
            if 8 > time.time() - beg > 6:
                logging.warning('Click avator wrongly,auto-fixed.')
                self.click(0.6978, 0.0267, 0.5)
            if time.time() - beg > 8:
                return -1
        # atk disappeared for over 1s, using skill succes:
        if time.time() - beg > 1:
            self.skill_used_turn[skill_ix] = turn
        return 1

    def use_skill(self, turn):
        '''
        Get images of skills (CD status) after using in turn 1, and compare current_img to CD_status_img to see that which skill can be used. 
        '''
        # update allowed-skills:
        allowed_skills = set(opt.skill)
        if opt.config_file:
            allowed_skills = self.config['allowed-skills'][str(
                CURRENT['scene'])]
            allowed_skills = set([int(x)
                                  for x in allowed_skills]) & set(opt.skill)

        now_skill_imgs = self.get_skill_imgs(False)

        info('Now use Skills. CD(turn): {}'.format(
            [turn - x for x in self.skill_used_turn if type(x) == int]))
        info(f'Alloewed skills: {allowed_skills}')

        # if all skills have no change, return directly:
        # if turn != 1 and now_skill_imgs == self.img['onCD-skills']:
        #     info('All skills are in CD, skip using.')
        #     return

        time.sleep(EXTRA_SLEEP_UNIT * 8)
        for no in allowed_skills:
            # never used, use it directly and save CD img for it:
            if self.img['onCD-skills'][no-1] is None:
                # print(f'+ skill {no} never used, use it.')
                self._use_one_skill(turn, no - 1)

            elif not (now_skill_imgs[no - 1] == self.img['onCD-skills'][no - 1]):
                # print(f'+ skill {no} not in CD, use it.')
                self._use_one_skill(turn, no - 1)

        time.sleep(EXTRA_SLEEP_UNIT * 2)
        # after using skills, get imgs of them in CD status:
        self.img['onCD-skills'] = self.get_skill_imgs(allowed_skills)

    def _choose_card(self):
        # normal atk card position:
        # for `ix` in range(-2, 3), card in No 1~5, get the screenshot for each card and calculate the mean of RGB values.
        pics = [self.grab((0.4411 + ix * 0.2015, 0.7333, 0.5588 + ix *
                           0.2015, 0.8324), to_PIL=True)[0] for ix in range(-2, 3)]
        RGBs = [np.array(x).mean(axis=(0, 1)) for x in pics]
        rgb_values = [np.array([256, 0, 0]), np.array(
            [0, 256, 0]), np.array([0, 0, 256])]
        card_colors = []
        # count the number of each color of cards:
        ccounter = {'R': 0, 'G': 0, 'B': 0}
        for x in RGBs:
            distances = [np.linalg.norm(x - v) for v in rgb_values]
            c = ['R', 'G', 'B'][np.argmin(distances)]
            ccounter[c] += 1
            card_colors.append(c)

        # use 3 cards with same color:
        max_c = max(ccounter, key=ccounter.get)
        if ccounter[max_c] >= 3:
            use_ixs = [i for i, x in enumerate(card_colors) if x == max_c][:3]
        # No 3 card in same color, then use red card first:
        else:
            red_ix = card_colors.index('R')
            others = set(range(5))
            others.remove(red_ix)
            use_ixs = [red_ix, *others][:3]

        info(f'Card colors: {"".join(card_colors)}, use: {use_ixs}')
        return use_ixs

    # old code: maybe useful for detecting servent avator in cards:
    def _choose_card_by_similar(self):
        pics = [np.array(self.grab((0.4411 + ix * 0.2015, 0.7333, 0.5588 + ix *
                                    0.2015, 0.8324), to_PIL=True)[0]) for ix in range(-2, 3)]
        # hists = [cal_single_hist(x) for x in pics]     # hist shape: [256, 3]
        max_sim = 0
        for j in range(5):
            for i in range(j):
                cards_ix = set(range(5)) - {i, j}
                ix1, ix2, ix3 = cards_ix
                now = np.mean([
                    cmp_single_hist(pics[ix1], pics[ix2]),
                    cmp_single_hist(pics[ix2], pics[ix3]),
                    cmp_single_hist(pics[ix1], pics[ix3]), ])
                # print('> {}: Var: {}'.format(cards_ix, now))
                if now > max_sim:
                    max_sim = now
                    nearest3ix = cards_ix
        return tuple(nearest3ix), max_sim

    def attack(self):
        used_ults = opt.ultimate
        if opt.config_file:
            ult_conf = self.config['ultimate'][str(CURRENT['scene'])]
            used_ults = () if ult_conf == 'none' else [
                int(x) for x in ult_conf]

        if opt.OCR:
            try:
                enemyHP, ourHP = self.ocrHP()
                if enemyHP < 50000 and ourHP > 24000:
                    used_ults = ()
            except Exception as e:
                print(e)
                logging.error('OCR failed, please check images in `./data`')

        info('Now start attacking....')
        # click attack icon:
        # time.sleep(EXTRA_SLEEP_UNIT*5)
        self.click(0.8823, 0.8444, 1)
        while self._monitor('atk', 0.1, 0, EchoError=False) != -1:
            logging.warning('Click ATK_Icon failed.')
            self.click(0.8823, 0.8444, 1)

        # use normal atk card:
        atk_card_x = [0.1003 + 0.2007 * x for x in range(5)]
        ues_ixs = self._choose_card()

        # time.sleep(EXTRA_SLEEP_UNIT*3)
        for i in range(3):
            self.click(atk_card_x[ues_ixs[i]], 0.7019, ATK_SLEEP_TIME)
            if i == 0 and used_ults:
                time.sleep(0.2)
                ult_x = [0.3171, 0.5005, 0.6839]
                for j in used_ults:
                    # j = 1, 2, 3
                    self.click(ult_x[j - 1], 0.2833, ULTIMATE_SLEEP)

        # To avoid `Can't use card` status:
        time.sleep(0.5)
        for _ in range(1):
            for i in range(5):
                self.click(atk_card_x[i], 0.7019, 0.2)
            time.sleep(1)
        info('Card using over.')

    def _monitor(self, names, max_time, sleep, bounds=0.5, AllowListenKey=False, ClickToSkip=False, EchoError=True, UseSimilar=False):
        '''
        used for monitoring area change.
        When `self.pre_img[name]` is similar to now_img, save now img_bitmap as new img and return.
        If already saved, When `self.img[name]` == now_img, return `name`.

        Args:
        ------
        * names: tuple, choose from self.area.keys()
        * max_time: maxtime to wait for.
        * sleep: sleep time when use `similar()` to judge. To avoid the situation: similar(now, ori) == True but now != ori, because `now_img` is still in randering, they are similar but not the same.
        * bounds <List[float]> : if 2 imgs' RGB distance < bounds, they are similar.
        * AllowListenKey: allow keyboard listening during the loop (for pause & end).
        * ClickToSkip: Click the screen to skip something.
        * EchoError: If printing error message when running out of time.
        * UseSimilar: <List[bool]> use similar() for each names or not, even if self.img already exists. (for final-scene and battle-end img)
        '''
        if SYSTEM != 'linux':
            AllowListenKey = False

        names = (names,) if type(names) == str else names
        bounds = bounds if isinstance(bounds, Iterable) else [
            bounds for _ in names]
        UseSimilar = UseSimilar if isinstance(UseSimilar, Iterable) else [
            UseSimilar for _ in names]
        assert len(names) == len(bounds) == len(UseSimilar)

        beg = time.time()
        pause_time = 0  # set for not calculating time for pause
        last_click_time = beg

        # start monitor:
        while 1:
            for name, bound, use_similar in zip(names, bounds, UseSimilar):
                # First running for `name`:
                if not self.img[name]:
                    now_img, now_bit = self.grab(self.area[name], to_PIL=True)
                    # now_bit.save('./debug/{}.png'.format(name))
                    similarity = similar(
                        self.LoadImg[name], now_img, bound, name)
                    # info(f'{name}: {similarity}, bound: {bound}')
                    if similarity:
                        if sleep:
                            time.sleep(sleep)
                            self._monitor(name, 1.5, 0, bound)
                        else:
                            self.img[name] = now_bit
                            logging.info(
                                'Get new smaple [{}], Similarity: {:.4f}'.format(name, similarity))
                        return name

                # already have self.img[name], but still want to use similar():
                elif use_similar:
                    now_img, _ = self.grab(self.area[name], to_PIL=True)
                    res = similar(self.LoadImg[name], now_img, bound, name)
                    if res:
                        logging.info(
                            'Detected [{}] using similar(), Similarity: {:.4f}.'.format(name, res))
                        return name

                # use self.img to compare:
                elif self.grab(self.area[name], to_PIL=False) == self.img[name]:
                    logging.info(
                        'Detected [{}], Func <_monitsor> returned.'.format(name))
                    return name

            # to listen keyboard and pause:
            if AllowListenKey and KeyEventListener.PAUSE:
                break_time = time.time()
                input('\033[5;37m ➜ Press enter to continue running: \033[0m')
                KeyEventListener.PAUSE = False
                pause_time += (time.time() - break_time)
            elif AllowListenKey and KeyEventListener.ENABLE_LAST_EPOCH_SWITCH:
                global END_AFTER_THIS_EPOCH
                END_AFTER_THIS_EPOCH = not END_AFTER_THIS_EPOCH
                KeyEventListener.ENABLE_LAST_EPOCH_SWITCH = False
                print('\033[5;37m ➜ Stop status switched: END_AFTER_THIS_EPOCH = [{}]\033[0m'.format(
                    END_AFTER_THIS_EPOCH))

            now = time.time()
            # run out of time:
            if now - beg - pause_time > max_time:
                if EchoError:
                    logging.error(
                        '{} running out of time: {}s'.format(names, max_time))
                return -1
            # every unit time pass:
            if ClickToSkip and (time.time() - last_click_time) >= CLICK_BREAK_TIME:
                self.click(0.7771, 0.9627, 0)
                last_click_time = now

            time.sleep(0.01)

    def wait_loading(self):
        logging.info('<LOAD> - Now loading...')
        # if CURRENT['epoch'] == 1:
        # if FUFU_NOT_DETECTED:
        #     time.sleep(10)
        #     self.img['fufu'] = self.grab('fufu')
        #     info('ATTENTION: Now saved sample for `fufu` since monitor failed.')
        # else:
        # self._monitor('fufu', 30, 0.5)

        if self._monitor('atk', 150, 0.5) == -1:
            os._exit(0)
        info('Finish loading, battle start.')

    def one_turn(self, turn):
        # Define functions to react each kinds of changes DURING a turn:
        def atk():
            global CLICK_BREAK_TIME
            CLICK_BREAK_TIME = PRE_BREAK_TIME
            info('Run func <atk>, Start new turn.')
            return 'NEXT-TURN'

        def fufu():
            global CLICK_BREAK_TIME
            CLICK_BREAK_TIME = 5
            info(
                'Set click-break={} & wait for [menu]'.format(CLICK_BREAK_TIME))
            time.sleep(1)
            # wait for [menu], if detected, then finish the battle.
            return 'WAIT-MENU'

        def battle_finish():
            global CLICK_BREAK_TIME
            CLICK_BREAK_TIME = 5
            info(
                'Set click-break={} & wait for [menu]'.format(CLICK_BREAK_TIME))
            time.sleep(0.5)
            self.click(0.7771, 0.9627, 0)
            # wait for [menu], if detected, then finish the battle.
            return 'WAIT-MENU'

        def menu():
            info('Run func <menu>, battle finish.')
            global CLICK_BREAK_TIME
            CLICK_BREAK_TIME = PRE_BREAK_TIME
            return 'BATTLE-OVER'

        def normal_scene():
            CURRENT['scene'] += 1
            CURRENT['scene'] = min(CURRENT['scene'], 2)
            info('Current scene: {}'.format(CURRENT['scene']))
            return 'WAIT-MENU'

        def final_scene():
            CURRENT['scene'] = 3       # 3 for the last (final) scene.
            info('Current scene: {}'.format(CURRENT['scene']))
            return 'WAIT-MENU'

        func_maps = {
            'menu': menu,
            'atk': atk,
            'fufu': fufu,
            'normal-scene': normal_scene,
            'final-scene': final_scene,
            'BattleFinish': battle_finish,
        }

        # init at the first turn.
        if turn == 1:
            self.skill_used_turn = [None] * 9
        self.use_skill(turn)

        # reset the attack order:
        order_opt = opt.order
        if opt.config_file:
            order_opt = int(self.config['atk-order'][str(CURRENT['scene'])])
        if order_opt and order_opt != 1:
            # AtkOrder[opt.order] represent the atk order.
            AtkOrder = (None, (0, 1, 2),
                        (0, 2, 1), (1, 2, 0),
                        (2, 1, 0), (2, 0, 1),
                        (1, 0, 2))
            # position: 0, 1, 2 from left to right.
            enemy_x = (0.1010, 0.3010, 0.4901)
            for ix in AtkOrder[order_opt]:
                self.click(enemy_x[ix], 0.0602, CLICK_BAR_SLEEP)
                # after 2019.11 update:
                self.click(0.7771, 0.9627, CLICK_BAR_SLEEP)

        self.attack()
        time.sleep(1.5)

        # Monitoring status change:
        args = {
            'max_time': 60,
            'sleep': 0,
            'AllowListenKey': True,
            'ClickToSkip': True,
            'names':      ('atk','final-scene','normal-scene','BattleFinish','menu'),
            'bounds':     (0.6,  0.65,         0.65,          0.7,           0.7),
            'UseSimilar': (False,True,         True,          True,          False),
        }
        info('Monitoring, no change got...')
        res = self._monitor(**args)

        if res == -1:
            atk_card_x = [0.1003 + 0.2007 * x for x in range(5)]
            for _ in range(3):
                self.click(0.6978, 0.0267, 1)
            for i in range(5):
                self.click(atk_card_x[i], 0.7019, 0.2)
            logging.warning('Something wrong. Trying to fix it.')
            res = self._monitor(**args)

        if res != -1:
            status = func_maps[res]()
            if status == 'WAIT-MENU':
                res = self._monitor(('atk', 'menu'), 50, 0, 0.5, False, True)
                status = func_maps[res]()
            return status
        else:
            logging.error(
                'Running out of time for 170s.')
            self.send_mail('Error')
            raise RuntimeError('Running out of time.')

    def one_battle(self, go_on=False):
        CURRENT['scene'] = 1

        if not go_on:
            self.enter_battle(opt.support)
            # wait for going into loading page:
            self.wait_loading()
        # ContinueRun:
        elif not self.img['atk']:
            if self._monitor('atk', 3, 0) == -1:
                os._exit(0)

        for i in range(50):
            CURRENT['turn'] = i+1
            info('Start Turn {}'.format(i + 1))
            # Here CD_num == i
            status = self.one_turn(i + 1)
            if status == 'BATTLE-OVER':
                return 1

        logging.error('Running over 50 turns, program was forced to stop.')
        self.send_mail('Error')
        raise RuntimeError(
            'Running over 50 turns, program was forced to stop.')

    def use_apple(self):
        # if self.grab(self.area['AP_recover']) == self.img['AP_recover']:
        if self._monitor('AP_recover', 1.5, 0.2, EchoError=False) != -1:
            logging.info('Using apple...')
            # choose apple:
            self.click(0.5, 0.4463, 0.7)
            self.click(0.5, 0.6473, 0.7)
            # choose OK:
            self.click(0.6563, 0.7824, 1)
            logging.info('Apple using over.')
            time.sleep(1.5)

            one_apple_battle_num = opt.clearAP  # go to see `opt.clearAP` help msg
            if opt.epoch - CURRENT['epoch'] < one_apple_battle_num - 1 and opt.clearAP:
                opt.epoch = CURRENT['epoch'] + one_apple_battle_num - 1
                logging.info(
                    'Auto change EPOCH to {} to use all AP.'.format(opt.epoch))

    def save_AP_recover_img(self):
        # choose AP bar:
        self.click(0.1896, 0.9611, 1)
        if self._monitor('AP_recover', 3, 0.2) == -1:
            os._exit(0)
        # click `exit`
        self.click(0.5, 0.8630, 0.5)

    def ocrHP(self):
        '''
        monitor HP of enemy and servent, using BaiduOCR API.
        '''
        enemy_x = (0.0852, 0.2756, 0.4654)
        our_x = (0.1545, 0.4015, 0.65)
        enemy_y = 0.04
        our_y = 0.85

        w = 0.1
        h = 0.055

        enemyHP = 0
        ourHP = 0
        for i in range(3):
            def getHP(i, x, y, name):
                self.grab((x, y, x + w, y + h), f'{name}HP_{i}')
                res = img2str(
                    ROOT + f'data/{name}HP_{i}.png').translate(self.digitFinder)
                return int(res) if res != '' else 0

            hp1 = getHP(i, enemy_x[i], enemy_y, 'enemy')
            hp2 = getHP(i, our_x[i], our_y, 'our')

            enemyHP += hp1
            ourHP += hp2
            info(f'OCR [{i + 1}] enemyHP: {hp1}, ourHP: {hp2}.')

        info(f'OCR [all] enemyHP: {enemyHP}, ourHP: {ourHP} on total.')

        # remove HP image files:
        for i in range(3):
            os.remove(ROOT + f'data/enemyHP_{i}.png')
            os.remove(ROOT + f'data/ourHP_{i}.png')
        return enemyHP, ourHP

    def run(self):
        beg = time.time()
        # if not self.img['AP_recover']:
        # self.save_AP_recover_img()
        for j in range(opt.epoch):
            print('\n ----- EPOCH{} START -----'.format(j + 1))
            CURRENT['epoch'] += 1
            self.one_battle()
            time.sleep(0.5)

            # Stop manually:
            if END_AFTER_THIS_EPOCH:
                print('➜ [Info] Manual Interruption after epoch {}.'.format(
                    CURRENT['epoch']))
                os._exit(0)

        end = time.time()
        logging.info('TotalTime: {:.1f}(min), <{:.1f}(min) on avarage.>'.format(
            (end - beg) / 60, (end - beg) / (60 * opt.epoch)))
        if opt.shutdown and SYSTEM == 'linux':
            # k = PyKeyboard()
            # k.press_keys(['Control_L', 'Delete'])
            self.send_mail('Done')
            os.system('shutdown 0')

        if SEND_MAIL:
            self.send_mail('Done')

    def buy(self):
        # 无限池抽卡
        btn_pos = (0.3681, 0.6034)
        reset_shop_pos = (0.8477, 0.3325)

        cnum = 0
        while True:
            self.click(*btn_pos, 0.1)
            cnum += 1
            if cnum == 5:
                self.click(*reset_shop_pos, 0.05)
                self.click(0.6573, 0.766, 0.05)
                self.click(0.4993, 0.7759, 0.05)
                cnum = 0

    def debug(self):
        # while 1:
        #     self.c.click(self.c.get_pos())
        #     time.sleep(0.1)
        # self.run()
        # self.ocrHP()
        self.buy()
        # ipdb.set_trace()


if __name__ == '__main__':
    # if you want to debug for pyscreenshot, set level to `INFO`. Script can't run in `DEBUG` level.
    update_var()
    get_log()
    fgo = Fgo(full_screen=FULL_SCREEN, sleep=False)
    if opt.debug:
        fgo.debug()
    elif opt.locate:
        fgo.monitor_cursor_pos()
    elif opt.ContinueRun:
        fgo.one_battle(go_on=True)
    else:
        fgo.run()
