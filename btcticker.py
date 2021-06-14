#!/usr/bin/python3
from PIL import Image, ImageOps
from PIL import ImageFont
from PIL import ImageDraw
import currency
import os
import sys
import logging
import RPi.GPIO as GPIO
from waveshare_epd import epd2in7
import time
import requests
import urllib, json
import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import yaml 
import socket
import textwrap
dirname = os.path.dirname(__file__)
picdir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'images')
fontdir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'fonts/googlefonts')
configfile = os.path.join(os.path.dirname(os.path.realpath(__file__)),'config.yaml')
font_date = ImageFont.truetype(os.path.join(fontdir,'PixelSplitter-Bold.ttf'),11)

def internet(hostname="google.com"):
    """
    Host: 8.8.8.8 (google-public-dns-a.google.com)
    OpenPort: 53/tcp
    Service: domain (DNS/TCP)
    """
    try:
        # see if we can resolve the host name -- tells us if there is
        # a DNS listening
        host = socket.gethostbyname(hostname)
        # connect to the host -- tells us if the host is actually
        # reachable
        s = socket.create_connection((host, 80), 2)
        s.close()
        return True
    except:
        logging.info("Google says No")
        pass
    return False

def human_format(num):
    num = float('{:.3g}'.format(num))
    magnitude = 0
    while abs(num) >= 1000:
        magnitude += 1
        num /= 1000.0
    return '{}{}'.format('{:f}'.format(num).rstrip('0').rstrip('.'), ['', 'K', 'M', 'B', 'T'][magnitude])

def _place_text(img, text, x_offset=0, y_offset=0,fontsize=40,fontstring="Forum-Regular", fill=0):
    '''
    Put some centered text at a location on the image.
    '''
    draw = ImageDraw.Draw(img)
    try:
        filename = os.path.join(dirname, './fonts/googlefonts/'+fontstring+'.ttf')
        font = ImageFont.truetype(filename, fontsize)
    except OSError:
        font = ImageFont.truetype('/usr/share/fonts/TTF/DejaVuSans.ttf', fontsize)
    img_width, img_height = img.size
    text_width, _ = font.getsize(text)
    text_height = fontsize
    draw_x = (img_width - text_width)//2 + x_offset
    draw_y = (img_height - text_height)//2 + y_offset
    draw.text((draw_x, draw_y), text, font=font,fill=fill )

def writewrappedlines(img,text,fontsize=16,y_text=20,height=15, width=25,fontstring="Roboto-Light"):
    lines = textwrap.wrap(text, width)
    numoflines=0
    for line in lines:
        _place_text(img, line,0, y_text, fontsize,fontstring)
        y_text += height
        numoflines+=1
    return img

def getData(config,other):
    """
    The function to update the ePaper display. There are two versions of the layout. One for portrait aspect ratio, one for landscape.
    """
    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'}
    whichcoin,krakenpair,fiat=configtocoinandfiat(config)
    logging.info("Getting Data")
    days_ago=int(config['ticker']['sparklinedays'])   
    endtime = int(time.time())
    starttime = endtime - 60*60*24*days_ago
    starttimeseconds = starttime
    endtimeseconds = endtime     
    # Get the price
    
    geckourlhistorical = "https://api.coingecko.com/api/v3/coins/"+whichcoin+"/market_chart/range?vs_currency="+fiat+"&from="+str(starttimeseconds)+"&to="+str(endtimeseconds)
    logging.info(geckourlhistorical)
    rawtimeseries = requests.get(geckourlhistorical, headers=headers).json()
    logging.info("Got price for the last "+str(days_ago)+" days from CoinGecko")
    timeseriesarray = rawtimeseries['prices']
    timeseriesstack = []
    length=len (timeseriesarray)
    i=0
    while i < length:
        timeseriesstack.append(float (timeseriesarray[i][1]))
        i+=1
    # A little pause before hiting the api again
    time.sleep(1)
    
    if config['ticker']['exchange']=='default':
        geckourl = "https://api.coingecko.com/api/v3/coins/markets?vs_currency="+fiat+"&ids="+whichcoin
        logging.info(geckourl)
        rawlivecoin = requests.get(geckourl, headers=headers).json()
        logging.info(rawlivecoin[0])
        liveprice = rawlivecoin[0]
        pricenow= float(liveprice['current_price'])
        alltimehigh = float(liveprice['ath'])
        other['market_cap_rank'] = int(liveprice['market_cap_rank'])
        other['volume'] = float(liveprice['total_volume'])
    elif config['ticker']['exchange']=='kraken':
        geckourl="https://api.kraken.com/0/public/Ticker?pair="+krakenpair;
        logging.info(geckourl)
        rawlivecoin = requests.get(geckourl, headers=headers).json()
        logging.info(rawlivecoin['result'])
        liveprice = rawlivecoin['result'][krakenpair]
        pricenow= float(liveprice['c'][0])
        alltimehigh = 1000000.0   # For non-default the ATH does not show in the API, so show it when price reaches *pinky in mouth* ONE MILLION DOLLARS
        other['market_cap_rank'] = 0 # For non-default the Rank does not show in the API, so leave blank
        other['volume'] = float(liveprice['v'][1])*pricenow
    else:
        geckourl= "https://api.coingecko.com/api/v3/exchanges/"+config['ticker']['exchange']+"/tickers?coin_ids="+whichcoin+"&include_exchange_logo=false"
        logging.info(geckourl)
        rawlivecoin = requests.get(geckourl, headers=headers).json()
        theindex=-1
        upperfiat=fiat.upper()
        for i in range (len(rawlivecoin['tickers'])):
            target=rawlivecoin['tickers'][i]['target']
            if target==upperfiat:
                theindex=i
                logging.info("Found "+upperfiat+" at index " + str(i))
#       if UPPERFIAT is not listed as a target theindex==-1 and it is time to go to sleep
        if  theindex==-1:
            logging.info("The exchange is not listing in "+upperfiat+". Misconfigured - shutting down script")
            sys.exit()
        liveprice= rawlivecoin['tickers'][theindex]
        pricenow= float(liveprice['last'])
        other['market_cap_rank'] = 0 # For non-default the Rank does not show in the API, so leave blank
        other['volume'] = float(liveprice['converted_volume']['usd'])
        alltimehigh = 1000000.0   # For non-default the ATH does not show in the API, so show it when price reaches *pinky in mouth* ONE MILLION DOLLARS
    logging.info("Got Live Data From CoinGecko")
    
    timeseriesstack.append(pricenow)
    if pricenow>alltimehigh:
        other['ATH']=True
    else:
        other['ATH']=False
    return timeseriesstack, other

def beanaproblem(message):
#   A visual cue that the wheels have fallen off
#   Also, for client side errors, force a reboot
    thebean = Image.open(os.path.join(picdir,'thebean.bmp'))
    image = Image.new('L', (264, 176), 255)    # 255: clear the image with white
    draw = ImageDraw.Draw(image)
    image.paste(thebean, (60,45))
    draw.text((95,15),str(time.strftime("%H:%M %a %d %b %Y")),font =font_date,fill = 0)
    writewrappedlines(image, "Issue:"+message)
#    draw.text((15,150),message, font=font_date,fill = 0)
    thebean.close()
#   Reload last good config.yaml
    with open(configfile) as f:
        config = yaml.load(f, Loader=yaml.FullLoader)
    return image

def makeSpark(pricestack):
    # Draw and save the sparkline that represents historical data
    # Subtract the mean from the sparkline to make the mean appear on the plot (it's really the x axis)    
    x = pricestack-np.mean(pricestack)
    fig, ax = plt.subplots(1,1,figsize=(10,3))
    plt.plot(x, color='k', linewidth=6)
    plt.plot(len(x)-1, x[-1], color='r', marker='o')
    # Remove the Y axis
    for k,v in ax.spines.items():
        v.set_visible(False)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.axhline(c='k', linewidth=4, linestyle=(0, (5, 2, 1, 2)))
    # Save the resulting bmp file to the images directory
    plt.savefig(os.path.join(picdir,'spark.png'), dpi=17)
    imgspk = Image.open(os.path.join(picdir,'spark.png'))
    file_out = os.path.join(picdir,'spark.bmp')
    imgspk.save(file_out) 
    plt.clf() # Close plot to prevent memory error
    ax.cla() # Close axis to prevent memory error

def updateDisplay(config,pricestack,other):
    """   
    Takes the price data, the desired coin/fiat combo along with the config info for formatting
    if config is re-written following adustment we could avoid passing the last two arguments as
    they will just be the first two items of their string in config
    """
    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'}
    with open(configfile) as f:
        originalconfig = yaml.load(f, Loader=yaml.FullLoader)
    originalcoin=originalconfig['ticker']['currency']
    originalcoin_list = originalcoin.split(",")
    originalcoin_list = [x.strip(' ') for x in originalcoin_list]
    whichcoin,krakenpair,fiat=configtocoinandfiat(config)
    days_ago=int(config['ticker']['sparklinedays'])   
    symbolstring=currency.symbol(fiat.upper())
    if fiat=="jpy" or fiat=="cny":
        symbolstring="¥"
    pricenow = pricestack[-1]
    currencythumbnail= 'currency/'+whichcoin+'.bmp'
    tokenfilename = os.path.join(picdir,currencythumbnail)
    sparkbitmap = Image.open(os.path.join(picdir,'spark.bmp'))
    ATHbitmap= Image.open(os.path.join(picdir,'ATH.bmp'))
#   Check for token image, if there isn't one, get on off coingecko, resize it and pop it on a white background
    if os.path.isfile(tokenfilename):
        logging.info("Getting token Image from Image directory")
        tokenimage = Image.open(tokenfilename).convert("RGBA")
    else:
        logging.info("Getting token Image from Coingecko")
        tokenimageurl = "https://api.coingecko.com/api/v3/coins/"+whichcoin+"?tickers=false&market_data=false&community_data=false&developer_data=false&sparkline=false"
        rawimage = requests.get(tokenimageurl, headers=headers).json()
        tokenimage = Image.open(requests.get(rawimage['image']['large'], headers = headers, stream=True).raw).convert("RGBA")
        resize = 100,100
        tokenimage.thumbnail(resize, Image.ANTIALIAS)
        new_image = Image.new("RGBA", (120,120), "WHITE") # Create a white rgba background with a 10 pixel border
        new_image.paste(tokenimage, (10, 10), tokenimage)   
        tokenimage=new_image
        tokenimage.thumbnail((100,100),Image.ANTIALIAS)
        tokenimage.save(tokenfilename)
    pricechangeraw = round((pricestack[-1]-pricestack[0])/pricestack[-1]*100,2)
    if pricechangeraw >= 100:
        pricechange = str("%+d" % pricechangeraw)+"%"
    else:
        pricechange = str("%+.2f" % pricechangeraw)+"%"
    if pricenow > 1000:
        pricenowstring =format(int(pricenow),",")
    else:
        # Print price to 5 significant figures
        pricenowstring =str(float('%.5g' % pricenow))
    if config['display']['orientation'] == 0 or config['display']['orientation'] == 180 :
        image = Image.new('L', (176,264), 255)    # 255: clear the image with white
        draw = ImageDraw.Draw(image)              
        draw.text((110,80),str(days_ago)+"day :",font =font_date,fill = 0)
        draw.text((110,95),pricechange,font =font_date,fill = 0)
        writewrappedlines(image, symbolstring+pricenowstring,40,65,8,10,"Roboto-Medium" )
        draw.text((10,10),str(time.strftime("%-I:%M %p, s%d %b %Y")),font =font_date,fill = 0)
        image.paste(tokenimage, (10,25))
        image.paste(sparkbitmap,(10,125))
        if config['display']['orientation'] == 180 :
            image=image.rotate(180, expand=True)
    if config['display']['orientation'] == 90 or config['display']['orientation'] == 270 :
        image = Image.new('L', (264,176), 255)    # 255: clear the image with white
        draw = ImageDraw.Draw(image) 
        if other['ATH']==True:
            image.paste(ATHbitmap,(190,85))  
        draw.text((110,90),str(days_ago)+" day : "+pricechange,font =font_date,fill = 0)
        if 'showvolume' in config['display'] and config['display']['showvolume']:
            draw.text((110,105),"24h vol : " + human_format(other['volume']),font =font_date,fill = 0)

        writewrappedlines(image, symbolstring+pricenowstring,50,55,8,10,"Roboto-Medium" )
        image.paste(sparkbitmap,(80,40))
        image.paste(tokenimage, (0,10))
                          
        if 'showrank' in config['display'] and config['display']['showrank'] and other['market_cap_rank'] > 0:
            draw.text((10,105),"Rank: " + str("%d" % other['market_cap_rank']),font =font_date,fill = 0)
        
        if (config['display']['trendingmode']==True) and not (str(whichcoin) in originalcoin_list):
            writewrappedlines(image, whichcoin,11,24,8,25,"PixelSplitter-Bold" )
#       draw.text((5,110),"In retrospect, it was inevitable",font =font_date,fill = 0)
        draw.text((90,15),str(time.strftime("%-I:%M %p, %d %b %Y")),font =font_date,fill = 0)
        if config['display']['orientation'] == 270 :
            image=image.rotate(180, expand=True)
#       This is a hack to deal with the mirroring that goes on in older waveshare libraries Uncomment line below if needed
#       image = ImageOps.mirror(image)
#   If the display is inverted, invert the image usinng ImageOps        
    if config['display']['inverted'] == True:
        image = ImageOps.invert(image)
#   Return the ticker image
    return image

def currencystringtolist(currstring):
    # Takes the string for currencies in the config.yaml file and turns it into a list
    curr_list = currstring.split(",")
    curr_list = [x.strip(' ') for x in curr_list]
    return curr_list

def currencycycle(curr_string):
    curr_list=currencystringtolist(curr_string)
    # Rotate the array of currencies from config.... [a b c] becomes [b c a]
    curr_list = curr_list[1:]+curr_list[:1]
    return curr_list    

def display_image(img):

    epd = epd2in7.EPD()  
    epd.Init_4Gray()
    epd.display_4Gray(epd.getbuffer_4Gray(img))
    epd.sleep()
    initkeys()
    return


def initkeys():
    key1 = 5
    key2 = 6
    key3 = 13
    key4 = 19
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(key1, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(key2, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(key3, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(key4, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    thekeys=[key1,key2,key3,key4]
    return thekeys

def configwrite(config):
    """  
        Write the config file following an adjustment made using the buttons
        This is so that the unit returns to its last state after it has been 
        powered off 
    """ 
    with open(configfile, 'w') as f:
        data = yaml.dump(config, f)

def fullupdate(config,lastcoinfetch):
    """  
    The steps required for a full update of the display
    Earlier versions of the code didn't grab new data for some operations
    but the e-Paper is too slow to bother the coingecko API 
    """
    other={}
    try:
        pricestack, ATH = getData(config, other)
        # generate sparkline
        makeSpark(pricestack)
        # update display
        image=updateDisplay(config, pricestack, other)
#          image=beanaproblem("Uncomment me to check how well the word wrapping works on error messages")
        display_image(image)
        lastgrab=time.time()
        time.sleep(0.2)
    except Exception as e:
        message="Data pull/print problem"
        image=beanaproblem(str(e)+" Line: "+str(e.__traceback__.tb_lineno))
        display_image(image)
        time.sleep(20)
        lastgrab=lastcoinfetch
    return lastgrab

def configtocoinandfiat(config):
    crypto_list = currencystringtolist(config['ticker']['currency'])
    kraken_list = currencystringtolist(config['ticker']['krakenpairs'])
    fiat_list=currencystringtolist(config['ticker']['fiatcurrency'])
    currency=crypto_list[0]
    krakenpair=kraken_list[0]
    fiat=fiat_list[0]
    return currency, krakenpair, fiat

def gettrending(config):
    print("ADD TRENDING")
    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'}
    coinlist=config['ticker']['currency']
    url="https://api.coingecko.com/api/v3/search/trending"
#   Cycle must be true if trending mode is on
    config['display']['cycle']=True
    trendingcoins = requests.get(url, headers=headers).json()
    for i in range(0,(len(trendingcoins['coins']))):
        print(trendingcoins['coins'][i]['item']['id'])
        coinlist+=","+str(trendingcoins['coins'][i]['item']['id'])  
    config['ticker']['currency']=coinlist
    return config

def main():
    loglevel = logging.WARNING
    # To debug, uncomment this line
    #loglevel = logging.DEBUG
    
    logging.basicConfig(level=loglevel)
    try:
        logging.info("epd2in7 BTC Frame")
#       Get the configuration from config.yaml
        with open(configfile) as f:
            config = yaml.load(f, Loader=yaml.FullLoader)
        logging.info(config)
        config['display']['orientation']=int(config['display']['orientation'])
#       Get the buttons for 2.7in EPD set up
        thekeys=initkeys()
#       Note how many coins in original config file
        howmanycoins=len(config['ticker']['currency'].split(","))
        print("HOWMANY="+str(howmanycoins))
#       Note that there has been no data pull yet
        datapulled=False 
#       Time of start
        lastcoinfetch = time.time()
        while True:
#           Poll Keystates
            key1state = GPIO.input(thekeys[0])
            key2state = GPIO.input(thekeys[1])
            key3state = GPIO.input(thekeys[2])
            key4state = GPIO.input(thekeys[3])
#           If there is an internet connection, respond to the keypresses
            if internet():                
                if key1state == False:
                    logging.info('Cycle currencies')
                    crypto_list = currencycycle(config['ticker']['currency'])
                    config['ticker']['currency']=",".join(crypto_list)
                    lastcoinfetch=fullupdate(config, lastcoinfetch)
                    configwrite(config) 
                if key2state == False:
                    logging.info('Rotate - 90')
                    config['display']['orientation'] = (config['display']['orientation']+90) % 360
                    lastcoinfetch=fullupdate(config,lastcoinfetch)
                    configwrite(config)
                if key3state == False:
                    logging.info('Invert Display')
                    config['display']['inverted'] = not config['display']['inverted']
                    lastcoinfetch=fullupdate(config,lastcoinfetch)
                    configwrite(config)
                if key4state == False:
                    logging.info('Cycle fiat')
                    fiat_list = currencycycle(config['ticker']['fiatcurrency'])
                    config['ticker']['fiatcurrency']=",".join(fiat_list)
                    lastcoinfetch=fullupdate(config,lastcoinfetch)
                    configwrite(config)
                if (time.time() - lastcoinfetch > (7+howmanycoins)*float(config['ticker']['updatefrequency'])) or (datapulled==False):
                        if config['display']['trendingmode']==True:
                            config=gettrending(config)
                if (time.time() - lastcoinfetch > float(config['ticker']['updatefrequency'])) or (datapulled==False):
                    if config['display']['cycle']==True:
                        crypto_list = currencycycle(config['ticker']['currency'])
                        config['ticker']['currency']=",".join(crypto_list)
                        # configwrite(config)
                    lastcoinfetch=fullupdate(config,lastcoinfetch)
                    datapulled = True
    except IOError as e:
        logging.info(e)
        image=beanaproblem(str(e)+" Line: "+str(e.__traceback__.tb_lineno))
        display_image(image)
    except Exception as e:
        logging.info(e)
        image=beanaproblem(str(e)+" Line: "+str(e.__traceback__.tb_lineno))
        display_image(image)
    except KeyboardInterrupt:    
        logging.info("ctrl + c:")
        image=beanaproblem("Keyboard Interrupt")
        display_image(image)
        epd2in7.epdconfig.module_exit()
        GPIO.cleanup()
        exit()

if __name__ == '__main__':
    main()
