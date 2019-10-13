import os
import sys
import torch
import io
import time
import numpy as np
from PIL import Image
import torch.onnx
from datetime import datetime
from torch.autograd import Variable
import torch.nn as nn
from miscc.config import cfg
from miscc.utils import build_super_images2
from model import RNN_ENCODER, G_NET
#from azure.storage.blob import BlockBlobService
import matplotlib.pyplot as plt

import pickle

def vectorize_caption(wordtoix, caption, copies=2):
    # create caption vector
    tokens = caption.split(' ')
    cap_v = []
    for t in tokens:
        t = t.strip().encode('ascii', 'ignore').decode('ascii')
        if len(t) > 0 and t in wordtoix:
            cap_v.append(wordtoix[t])

    # expected state for single generation
    captions = np.zeros((copies, len(cap_v)))
    for i in range(copies):
        captions[i,:] = np.array(cap_v)
    cap_lens = np.zeros(copies) + len(cap_v)

    #print(captions.astype(int), cap_lens.astype(int))
    #captions, cap_lens = np.array([cap_v, cap_v]), np.array([len(cap_v), len(cap_v)])
    #print(captions, cap_lens)
    #return captions, cap_lens

    return captions.astype(int), cap_lens.astype(int)

def generate(caption, wordtoix, ixtoword, text_encoder, netG, blob_service, copies=2, mode="bilinear"):

    # load word vector
    captions, cap_lens  = vectorize_caption(wordtoix, caption, copies)
    n_words = len(wordtoix)

    # only one to generate
    batch_size = captions.shape[0]

    nz = cfg.GAN.Z_DIM
    with torch.no_grad():
        captions = Variable(torch.from_numpy(captions))
        cap_lens = Variable(torch.from_numpy(cap_lens))
        noise = Variable(torch.FloatTensor(batch_size, nz))

    if cfg.CUDA:
        captions = captions.cuda()
        cap_lens = cap_lens.cuda()
        noise = noise.cuda()



    #######################################################
    # (1) Extract text embeddings
    #######################################################
    hidden = text_encoder.init_hidden(batch_size)
    words_embs, sent_emb = text_encoder(captions, cap_lens, hidden)
    mask = (captions == 0)


    #######################################################
    # (2) Generate fake images
    #######################################################
    noise.data.normal_(0, 1)
    fake_imgs, attention_maps, _, _ = netG(noise, sent_emb, words_embs, mask)
    #plt.imshow(fake_imgs[0].detach().numpy())

    # G attention
    cap_lens_np = cap_lens.cpu().data.numpy()

    prefix = datetime.now().strftime('%Y/%B/%d/%H_%M_%S_%f')
    for j in range(batch_size):
        for k in range(len(fake_imgs)):
            im = fake_imgs[k][j].data.cpu().numpy()
            #if k != 2:
                #im = nn.functional.interpolate(im, size=(256, 256), mode="bilinear")
            im = (im + 1.0) * 127.5
            im = im.astype(np.uint8)
            im = np.transpose(im, (1, 2, 0))
            im = Image.fromarray(im)
            #plt.imshow(im)
            if k != len(fake_imgs) - 1:
                #im = nn.functional.interpolate(im[j].unsqueeze(0, size=(256, 256), mode="bilinear")
                im.save("{}org{}_g{}.png".format(j, "bird", k))
                im1 = im.resize((256, 256))
                im1.save("{}def{}_g{}.png".format(j, "bird", k))
                im2 = im.resize((256, 256), Image.BILINEAR)
                im2.save("{}bi{}_g{}.png".format(j, "bird", k))
            else:
                im.save("{}{}_g{}.png".format(j, "bird", k))

            # save image to stream
            #stream = io.BytesIO()
            #im.save(stream, format="png")
            #stream.seek(0)
            #if copies > 2:
                #blob_name = '%s/%d/%s_g%d.png' % (prefix, j, "bird", k)
            #else:
                #blob_name = '%s/%s_g%d.png' % (prefix, "bird", k)
            #blob_service.create_blob_from_stream(container_name, blob_name, stream)
            #urls.append(full_path % blob_name)

        if copies == 2:
            break
    urls = None
    return urls

def word_index():
    # load word to index dictionary
    x = pickle.load(open('data/captions.pickle', 'rb'))
    ixtoword = x[2]
    wordtoix = x[3]
    del x

    return wordtoix, ixtoword

def models(word_len):
    #print(word_len)

    text_encoder = RNN_ENCODER(word_len, nhidden=cfg.TEXT.EMBEDDING_DIM)
    state_dict = torch.load(cfg.TRAIN.NET_E, map_location=lambda storage, loc: storage)
    text_encoder.load_state_dict(state_dict)
    if cfg.CUDA:
        text_encoder.cuda()
    text_encoder.eval()

    netG = G_NET()
    state_dict = torch.load(cfg.TRAIN.NET_G, map_location=lambda storage, loc: storage)
    netG.load_state_dict(state_dict)
    if cfg.CUDA:
        netG.cuda()
    netG.eval()
    return text_encoder, netG

def eval(caption):
    # load word dictionaries
    wordtoix, ixtoword = word_index()
    # lead models
    text_encoder, netG = models(len(wordtoix))
    # load blob service
    blob_service = BlockBlobService(account_name='attgan', account_key=os.environ["BLOB_KEY"])

    t0 = time.time()
    urls = generate(caption, wordtoix, ixtoword, text_encoder, netG, blob_service)
    t1 = time.time()

    response = {
        'small': urls[0],
        'medium': urls[1],
        'large': urls[2],
        'map1': urls[3],
        'map2': urls[4],
        'caption': caption,
        'elapsed': t1 - t0
    }

    return response

if __name__ == "__main__":
    caption = "the bird has a yellow crown and a black eyering that is round"

    # load configuration
    #cfg_from_file('eval_bird.yml')
    # load word dictionaries
    wordtoix, ixtoword = word_index()
    # lead models
    text_encoder, netG = models(len(wordtoix))
    # load blob service
    #blob_service = BlockBlobService(account_name='attgan', account_key='[REDACTED]')
    blob_service = None

    t0 = time.time()
    urls = generate(caption, wordtoix, ixtoword, text_encoder, netG, blob_service)
    t1 = time.time()
    print(t1-t0)
    ##print(urls)