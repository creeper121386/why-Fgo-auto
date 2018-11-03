
# coding: utf-8

# In[1]:


# [TODO] 
# - 使用感知hash智能出牌

import os 
import win32api, win32con, win32gui, win32ui
import PIL
import time
from config import *
import numpy as np
import logging
from utils import compare_img, pic_shot, compare_img_new
from email.header import Header
import smtplib 
from email.mime.multipart import MIMEMultipart, MIMEBase
from email.mime.text import MIMEText
from email import encoders

SKILL_CD = YOUR_SKILL_CD + (SUPPORT_SKILL_CD, )*3
CURRENT_EPOCH = 0
MONITOR_INFO = 'MNTR' if EPOCH<10 else 'MONTR'


def get_log():
    logging.basicConfig(level=logging.DEBUG, format='[%(asctime)s - %(levelname)s]: %(message)s', 
                            datefmt='%H:%M:%S', filename='fgo.LOG', filemode='w')
    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG)
    console.setFormatter(logging.Formatter('[%(asctime)s - %(levelname)s]: %(message)s', datefmt='%m-%d %H:%M:%S'))
    logging.getLogger().addHandler(console)
# In[2]:


class Cursor(object):
    def __init__(self, init_pos):
        # init_pos：should be a tuple, set `False` to skip initing position.
        if init_pos!=False and len(init_pos)==2:
            self.move_to(init_pos)
    
    def move_to(self, pos):
        win32api.SetCursorPos(pos)
    
    def get_pos(self):
        return win32api.GetCursorPos()
    
    def click(self):
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    
    def right_click(self):
        win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0) 
        win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)


class Fgo(object):
    def __init__(self, full_screen=True, sleep=True):
        # [init by yourself] put cursor at the down-right position of the game window.
        if full_screen:
            self.height = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)
            self.width = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
            self.scr_pos1 = (0, 0)
            self.scr_pos2 = (self.width, self.height)
            self.c = Cursor(init_pos=False)
            for x in range(5):             
                logging.info('Start in %d s, Please enter FULL SCREEN.' % (5-x))
                time.sleep(1)
                   
        else:
            self.c = Cursor(init_pos=False)
            while 1:
                in1 = input('==> Move cursor to top-left of Fgo, press ENTER (q to exit): ')
                if in1 == 'q':
                    print('==> Running stop')
                    os._exit(0)
                self.scr_pos1 = self.c.get_pos()
                print('==> Get cursor at {}'.format(self.scr_pos1))
                
                in2 = input('==> Move cursor to down-right of Fgo, press ENTER (q to exit): ')
                if in2 == 'q':
                    print('==> Running stop')
                    os._exit(0)
                self.scr_pos2 = self.c.get_pos()
                print('==> Get cursor at {}'.format(self.scr_pos2))
                
                res = input('Continue? [y(continue) /n(reset) /q(quit)]:'.format(
                    time.strftime('%H:%M:%S')))
                if res == 'n':
                    continue
                elif res == 'q':
                    os._exit(0)
                else: 
                    break
            if sleep:
                for x in range(3):
                    logging.info('Start in %d s, make sure the window not covered.' % (3-x))
                    time.sleep(1)
            self.width = abs(self.scr_pos2[0] - self.scr_pos1[0])
            self.height = abs(self.scr_pos2[1] - self.scr_pos1[1])
        #---------------------sampled pix info-----------------------
        # position info, type: 'name': (x1, y1, x2, y2)
        self.area_pos = {
            'menu': (0.0693, 0.7889, 0.1297, 0.8917),
            # 'StartMission': (0.875, 0.9194, 0.9807, 0.9565), 
            # 'AP_recover': (0.4583, 0.0556, 0.5391, 0.0926),
            'AP_recover': (0.2511, 0.177, 0.3304, 0.3158),
            'AtkIcon': (0.8708, 0.7556, 0.8979, 0.8009),
            'sample2': (0.8984, 0.9352, 0.9542, 0.9630),
            'support': (0.6257, 0.1558, 0.6803, 0.1997)
        }   

        # `pre` means this image was saves before code running.
        self.img = {
            'pre_loading': PIL.Image.open('./data/loading.jpg'),
            'pre_atk': PIL.Image.open('./data/atk_ico.jpg'), 
            'menu': self.pic_shot_float(self.area_pos['menu']), 
            'StartMission': None, 
            'AP_recover': None,
            'atk_ico': None
        }
        # get a screen shot of menu icon:
        if DEBUG:
            self.img['menu'].save('./data/menu.jpg')
        #print('[DEBUG {}] Window width(x) = {}, height(y) = {}'.format(
        #    time.strftime('%H:%M:%S'), self.width, self.height))
    
    def monitor_cursor_pos(self):
        while 1:
            x, y = self.c.get_pos()
            if self.scr_pos2[0]> x >self.scr_pos1[0] and self.scr_pos2[1]> y >self.scr_pos1[1]:
                x = (x-self.scr_pos1[0])/self.width
                y = (y-self.scr_pos1[1])/self.height
                pos = (round(x, 4), round(y, 4))
            else:
                pos = 'Not in Fgo window.'
            logging.info('<{}> Now float pos: {}, real: {}'.format(MONITOR_INFO, pos, self.c.get_pos()))
            time.sleep(0.5)

    def _set(self, float_x, float_y):
        # input type: float
        # reurn the real position on the screen.
        return int(self.scr_pos1[0]+self.width*float_x), int(self.scr_pos1[1]+self.height*float_y)
    
    def click_act(self, float_x, float_y, sleep_time, click=True, info=True):
        pos = self._set(float_x, float_y)
        self.c.move_to(pos)
        if click:
            try:
                self.c.click()
            except:
                logging.warning('Screen was locked. You can ignore this message.')
                pass
        # if not DEBUG and info:
            # logging.info('<E{}/{}> - Simulate cursor click at {}'.format(CURRENT_EPOCH, EPOCH, (float_x, float_y)))
        time.sleep(sleep_time)
        
    def send_mail(self, status):
        '''
        - status: 'err' or 'done'
        '''
        self.pic_shot_float((0, 0, 1, 1), './data/final_shot.jpg')
        with open('fgo.LOG', 'r') as f:
            res = f.readlines()
            res = [x.replace('<', '&lt;') for x in res]
            res = [x.replace('>', '&gt;') for x in res]
            res = ''.join([x[:-1]+'<br />' for x in res])
        msg = MIMEMultipart()
        with open('./data/final_shot.jpg', 'rb') as f:
            mime = MIMEBase('image', 'jpg', filename = 'shot.jpg')
            mime.add_header('Content-Disposition', 'attachment', filename='shot.jpg')
            mime.add_header('Content-ID', '<0>')
            mime.add_header('X-Attachment-Id', '0')
            mime.set_payload(f.read())
            encoders.encode_base64(mime)
            msg.attach(mime)

        msg.attach(MIMEText('<html><body><p><img src="cid:0"></p>' +
            '<font size=\"1\">{}</font>'.format(res) +
            '</body></html>', 'html', 'utf-8'))
        msg['From'] = Header('why酱的FGO脚本', 'utf-8')
        msg['Subject'] = Header('<FGO {}> Running Stop <STATUS:{}>'.format(time.strftime('%m-%d|%H:%M'), status), 'utf-8')
        server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT)
        try:
            server.ehlo()
            # server.starttls()
            server.login(FROM_ADDRESS, PASSWD)
            server.sendmail(FROM_ADDRESS, [TO_ADDRESS], msg.as_string())
            server.quit()
            print('==> Mail sent successfully. Please check it.')
        except Exception as e:
            print('\nError type: ', e)
            print('==> Mail sent failed. Maybe there are something wrong.')


    def enter_battle(self, supNo=8):
        # [init by yourself] put the tag of battle at the top of screen.

        # postion of the center of battle tag.
        bat_tag_y = 0.2740
        bat_tag_x = 0.7252
        self.click_act(bat_tag_x, bat_tag_y, 1)
        self.use_apple()
        # choose support:
        # postion of support servant tag.
        sup_tag_x = 0.4893
        sup_tag_y = 0.3944
        # postion of support class icon.
        sup_ico_x = 0.0729+0.0527*supNo
        sup_ico_y = 0.1796
        
        self.click_act(sup_ico_x, sup_ico_y, 0.8)
        self.click_act(sup_tag_x, sup_tag_y, 1)

        # save `StartMission icon`
        # postion of `mission start` tag
        start_y = 0.9398
        start_x = 0.9281
        if not self.img['StartMission']:
            self.img['StartMission'] = self.pic_shot_float(self.area_pos['sample2'])
            if DEBUG:
                self.img['StartMission'].save('./data/StartMission.jpg')
            self.click_act(start_x, start_y, 1)
        else:
            time1 = time.time()
            while 1:
                if self.pic_shot_float(self.area_pos['sample2']) == self.img['StartMission']:
                    self.click_act(start_x, start_y, 1)
                    return 0
                elif time.time() - time1 > 10:
                    logging.error('<{}> - Can\'t get START_MISSION tag for 10s.'.format(MONITOR_INFO))
                    self.send_mail('Error')
                    raise RuntimeError('Can\'t get START_MISSION tag for 10s')
      
    def use_skill(self, skills):
        # position of skills:
        logging.info('<E{}/{}> - Now using skills...'.format(CURRENT_EPOCH, EPOCH))
        ski_x = [0.0542, 0.1276, 0.2010, 0.3021, 0.3745, 0.4469, 0.5521, 0.6234, 0.6958]
        ski_y = 0.8009
        # snap = 0.0734
        time.sleep(0.5)
        for i in skills:
            self.click_act(ski_x[i], ski_y, 0.05)
            self.click_act(0.5, 0.5, 0.05)
            self.click_act(0.0521, 0.4259, 0.2)
            
            while self.pic_shot_float(self.area_pos['AtkIcon']) != self.img['atk_ico']:
                continue

        logging.info('<E{}/{}> - Skills using over.'.format(CURRENT_EPOCH, EPOCH))
       
    def attack(self):
        logging.info('<E{}/{}> - Now start attacking....'.format(CURRENT_EPOCH, EPOCH))

        # attack icon position:
        atk_ico_x = 0.8823
        atk_ico_y = 0.8444
        self.click_act(atk_ico_x, atk_ico_y, 1)
        
        
        # use normal atk card:
        # normal atk card position:
        atk_card_x = [0.1003+0.2007*x for x in range(5)]
        atk_card_y = 0.7019
        for i in range(5):
            self.click_act(atk_card_x[i], atk_card_y, ATK_SLEEP_TIME)
            if i==0 and USE_ULTIMATE:
                # logging.info('==> Using Utimate skills...')
                time.sleep(0.5)
                ult_x = [0.3171, 0.5005, 0.6839]
                ult_y = 0.2833
                for x in ult_x:
                    self.click_act(x, ult_y, 0.1)
        logging.info('<E{}/{}> - ATK Card using over.'.format(CURRENT_EPOCH, EPOCH))

    def pic_shot_float(self, pos, name=None):
        float_x1, float_y1, float_x2, float_y2 = pos
        # error: 关闭屏幕缩放！关闭屏幕缩放！
        x1, y1 = self._set(float_x1, float_y1)
        #self.click_act(x1, y1, 1)
        x2, y2 = self._set(float_x2, float_y2)
        # self.click_act(x2, y2, 1)
        return pic_shot(x1, y1, x2, y2, name)
         
    def wait_loading(self, save_img=False, algo=0, sleep=None, mode=0):
        '''
        sample in the attack icon per 1s, if loading process is over, break the loop.
        '''
        real_atk = self.img['pre_atk']
        real_loading = self.img['pre_loading']
        
        for i in range(100):
            now_atk_img = self.pic_shot_float(self.area_pos['AtkIcon'])
            if DEBUG:
                now_atk_img.save('./data/now_loading.jpg')
            if not i:
                logging.info('<LOAD> - Monitoring at area1, Now loading...')
            if CURRENT_EPOCH != 1:
                if now_atk_img==self.img['atk_ico']:
                    logging.info('<{}> - Detected status change, finish loading.'.format(MONITOR_INFO))
                    return 0    
                else:
                    time.sleep(1)
              
            else:
                diff1 = compare_img_new(now_atk_img, real_atk, algo)
                diff2 = compare_img_new(now_atk_img, real_loading, algo)
                if DEBUG:
                    logging.debug('Diff of now_img and ATK is: {}'.format(diff1))
                    logging.debug('Diff of now_img and LOADING is: {}'.format(diff2))
                condition = (diff2 == 0 and diff1 > 0) if mode == -1 else (diff1 < diff2 and diff2!=0)
                if condition:
                    time.sleep(0.8)
                    logging.info('<{}> - Detected status change, loaded over.'.format(MONITOR_INFO))
                    if sleep:
                        # wait for background anime finishing:
                        time.sleep(sleep)
                    return diff1
                time.sleep(1)
            
        logging.error('Connection timeout. Maybe there are some problems with your network.')
        self.send_mail('Err')
        raise RuntimeError('Connection timeout during loading.')
    
    def cal_diff(self, x1, y1, x2, y2, target, save_img=False, hash=True):
        '''
        sample in the position of attack icon to find that if the game is in the loading page.
        return a BOOL type data.
        - x1, y1, x2, y2: the position of the origin area.
        - save_img: if you want to save images.
        - hash: use hash algorithm or compare image simply. 
        '''        
        real_loading = target
        now_atk_img = self.pic_shot_float((x1, y1, x2, y2))
        if DEBUG:
            now_atk_img.save('./data/sample.jpg')
        if hash:
            return compare_img_new(now_atk_img, real_loading, 0)
        else:
            return 0 if now_atk_img==self.img['pre_atk'] else -1
     
    def cal_atk_diff(self, targrt, save_img=False, hash=True):
        # sample1 area of attack icon:
        a, b, c, d = self.area_pos['AtkIcon']     
        return self.cal_diff(a, b, c, d, self.img['pre_atk'], save_img=save_img, hash=hash)
        
    def one_turn_new(self):   
        # uodate saved atk icon:
        if not self.img['atk_ico']:
            self.img['atk_ico'] = self.pic_shot_float(self.area_pos['AtkIcon'])
            if DEBUG:
                self.img['atk_ico'].save('./data/save_new_atk.jpg')
            
        if ATK_BEHIND_FIRST:
            self.click_act(0.3010, 0.0602, 0.1)
            self.click_act(0.1010, 0.0593, 0.1)
        self.use_skill(USED_SKILL)
        self.attack()
        time.sleep(5)
        
        # Start waiting status change:
        beg_time = time.time()
        # compare atk icon to the last saved icon.
        j = 0
        while 1:
            if time.time() - beg_time > 150:
                logging.error('Running out of time, No status change detected for 2min30s.')
                self.send_mail('Err')
                raise RuntimeError('Running out of time.')

            elif self.pic_shot_float(self.area_pos['AtkIcon']) == self.img['atk_ico']:
                logging.info('<{}> - Got status change, Start new turn...'.format(MONITOR_INFO))
                return 0

            elif self.pic_shot_float(self.area_pos['sample2']) == self.img['StartMission']:
                self.click_act(0.0766, 0.0565, 1)
                self.click_act(0.0766, 0.0565, 1)
                logging.warning('<{}> - Entered wrong battle, auto-fixed. battle finish.'.format(MONITOR_INFO))
                return 1
                
            elif self.pic_shot_float(self.area_pos['menu']) == self.img['menu']:
                logging.info('<{}> - Detected status changing, battle finish.'.format(MONITOR_INFO))
                return 1 
            
            else:
                # click to skip something
                self.click_act(0.7771, 0.9627, 1.2, info=False)
                if not j:
                    logging.info('<{}> - Monitoring (0.7771, 0.9627), no change...'.format(MONITOR_INFO))
                j += 1
                # time.sleep(SURVEIL_TIME_OUT)
 

    def one_battle(self, go_on=False):
        '''
        main part of running the program. 
        '''
        if not go_on:
            self.enter_battle(SUPPORT)
            # wait for going into loading page:
            time.sleep(3.5)
            self.diff_atk = self.wait_loading(save_img=DEBUG, sleep=3)
        else:
            self.img['atk_ico'] = self.img['atk_ico']
        
        for i in range(50):
            logging.info('<E{}/{}> - Start Turn {}'.format(CURRENT_EPOCH, EPOCH, i+1))         
            # Here CD_num == i
            over = self.one_turn_new()    
            if over:
                return 1
        logging.error('Running over 50 turns, program was forced to stop.')
        self.send_mail('Err')
        raise RuntimeError('Running over 50 turns, program was forced to stop.')
        
    def use_apple(self):
        # ap_img = self.pic_shot_float(self.area_pos['AP_recover'])
        # ap_img.save('./data/now_ap.jpg')
        if self.pic_shot_float(self.area_pos['AP_recover']) == self.img['AP_recover']:
            logging.info('==> Using apple...')
            # choose apple:
            self.click_act(0.5, 0.4463, 0.7)
            # choose OK:
            self.click_act(0.6563, 0.7824, 1)
            logging.info('==> Apple using over.')

            global EPOCH, CURRENT_EPOCH
            if EPOCH - CURRENT_EPOCH < ONE_APPLE_BATTLE - 1:
                EPOCH = CURRENT_EPOCH + ONE_APPLE_BATTLE -1
                logging.info('Auto change EPOCH to {} to use all AP.'.format(EPOCH))
            
    def clear_data(self):
        files = os.listdir('./data')
        for x in files:
            if x == 'atk_ico.jpg' or x == 'loading.jpg':
                continue
            else:
                os.remove('./data/{}'.format(x))

    def save_AP_recover_pic(self):
        logging.info('==> Saving AP_recover pic...')
        # choose AP bar:
        self.click_act(0.1896, 0.9611, 1)
        self.img['AP_recover'] = self.pic_shot_float(self.area_pos['AP_recover'])
        # self.img['AP_recover'].save('./data/ap.jpg')
        # click `exit`
        self.click_act(0.5, 0.8630, 0.5)

    def run(self):
        beg = time.time()
        self.save_AP_recover_pic()
        for j in range(EPOCH):
            print('\n----------------------< Battle EPOCH{} Start >----------------------'.format(j+1))
            global CURRENT_EPOCH
            CURRENT_EPOCH += 1
            self.one_battle()
            time.sleep(1)
            # between battles:
        end = time.time()
        logging.info('Total time use: {:.1f}min, <{:.1f}min on avarage.>'.format((end-beg)/60, (end-beg)/(60*EPOCH)))
        if SEND_MAIL:
            self.send_mail('Done')
        self.clear_data()


if __name__ == '__main__':
    get_log()
    fgo = Fgo(full_screen=FULL_SCREEN, sleep=False)
    # fgo.one_battle(go_on=True)
    # fgo.send_mail('test')
    # fgo.monitor_cursor_pos()
    fgo.run()