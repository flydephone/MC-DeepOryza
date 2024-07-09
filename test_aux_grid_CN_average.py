# -*- coding: utf-8 -*-
"""
Created on Mon Oct 12 09:56:07 2020
1、在原有基础上加入人工激活层，保证基本物理规律（物候正增长，总干物质正增长，各器官质量守恒）
2、参数作为输入，不作为隐藏状态
@author: hanjingye
"""


import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import datetime
import os
import math
import pickle
import random
import copy

import torch
from torch import nn
import torch.nn.functional as F
from torch.autograd import Variable
from torch.utils.data import DataLoader

import datetime
import time
from models_aux.MyDataset import MyDataSet
from models_aux.MC_base_prior09_01 import DEEPORYZA
import utils


device = torch.device('cuda') if torch.cuda.is_available() else torch.device('cpu')

if __name__ == "__main__":
    # %%load base data
    tra_year = "2019"
    cali = "2018"
    model_type = "MC_base_prior09_01_convergence_obs_scratch"
    scal_type="nor"
    obs_mask_name = []
    obs_name = ['DVS','PAI','WLV','WST','WSO','WAGT',"WRR14"]
    obs_used_name = [name for name in obs_name if name not in obs_mask_name]
    # obs_name = ['WLV']
    units = ['-',"m$^2$/m$^2$","kg/ha","kg/ha","kg/ha","kg/ha","kg/ha"]
    sample_2018, sample_2019 = 65,40
    use_pretrained = False

    model_list = os.listdir("model_weight/%s/"%model_type)
    if cali=="uncali":
        model_list = [tpt for tpt in model_list if tra_year in tpt and "uncali" in tpt]
    else:
        model_list = [tpt for tpt in model_list if tra_year in tpt and "uncali" not in tpt]


    r2_list, rmse_list,np_pre_points_list,np_pre_dataset_list = [], [], [], []
    for model in model_list[:]:
        model_path = 'model_weight/%s/%s'%(model_type,model)

        # trained_model_name = os.listdir(model_path)[epoch]
        tra_loss = []
        tes_loss = []
        trained_model_names = os.listdir(model_path)
        for tpt in trained_model_names[:]:
            tra_loss += [float(tpt[:-4].split("_")[-5])]
            tes_loss += [float(tpt[:-4].split("_")[-1])]
        loss = np.array([tra_loss,tes_loss]).T
        min_indices = np.argmin(loss[:,0], axis=0)
        # trained_model_name = trained_model_names[-1]
        trained_model_name = trained_model_names[min_indices]
       
        # model_path = 'E:/pytorch/model_wtight/my_model/ORYZA_LSTM'
        # trained_model_name = "2022-07-08 05-09-51_uniform_structure_two_model3_2018_2019.pkl"
        rea_res_dataset,rea_par_dataset,rea_wea_fer_dataset,rea_obs_dataset,rea_fit_dataset = utils.dataset_loader(data_source="format_dataset/%s/real_%s"%(scal_type,tra_year))
      
        if tra_year == "2018":
            tra_res_dataset,tra_wea_fer_dataset,tra_obs_dataset,tra_fit_dataset = rea_res_dataset[:sample_2018],rea_wea_fer_dataset[:sample_2018],rea_obs_dataset[:sample_2018],rea_fit_dataset[:sample_2018]
            tes_res_dataset,tes_wea_fer_dataset,tes_obs_dataset,tes_fit_dataset = rea_res_dataset[sample_2018:],rea_wea_fer_dataset[sample_2018:],rea_obs_dataset[sample_2018:],rea_fit_dataset[sample_2018:]
        elif tra_year == "2019":
            tes_res_dataset,tes_wea_fer_dataset,tes_obs_dataset,tes_fit_dataset = rea_res_dataset[:sample_2018],rea_wea_fer_dataset[:sample_2018],rea_obs_dataset[:sample_2018],rea_fit_dataset[:sample_2018]
            tra_res_dataset,tra_wea_fer_dataset,tra_obs_dataset,tra_fit_dataset = rea_res_dataset[sample_2018:],rea_wea_fer_dataset[sample_2018:],rea_obs_dataset[sample_2018:],rea_fit_dataset[sample_2018:]
    
            
        max_min,mean_std,par_col_name,res_col_name = utils.base_dataset_loader()
        res_col_name = ['TIME','DVS','PAI','WLV','WST','WSO','WAGT',"WRR14"]
        # %%obs loc
        obs_loc = [res_col_name.index(name) for name in obs_name]
        #%% import dataset-raw
        res_max,res_min,par_max,par_min,wea_fer_max,wea_fer_min = max_min
        res_mean,res_std,par_mean,par_std,wea_fer_mean,wea_fer_std = mean_std
        
        
        #%% super parameter
        wea_fer_dim = np.shape((utils.pickle_load(tra_wea_fer_dataset[0])))[1]-1-3
        cro_dim = np.shape(utils.pickle_load(tra_res_dataset[0]))[1]
        obs_dim = len(obs_name)
        
        input_dim = wea_fer_dim
        output_dim = obs_dim
        init_dim = obs_dim
            
        #%% generate dataset
        batch_size = 128
        tra_set = MyDataSet(obs_loc=obs_loc, res=tra_res_dataset, wea_fer=tra_wea_fer_dataset, obs=tra_obs_dataset, fit=tra_fit_dataset, max_min=max_min, mean_std=mean_std, scal_type=scal_type, batch_size=batch_size, aug=False)
        tra_DataLoader = DataLoader(tra_set, batch_size=batch_size, shuffle=False)
        tes_set = MyDataSet(obs_loc=obs_loc, res=tes_res_dataset, wea_fer=tes_wea_fer_dataset, obs=tes_obs_dataset, fit=tes_fit_dataset, max_min=max_min, mean_std=mean_std, scal_type=scal_type, batch_size=batch_size, aug=False)
        tes_DataLoader = DataLoader(tes_set, batch_size=batch_size, shuffle=False)
    
        # %% creat instances from class_LSTM
        hidden_dim_dvs = 64
        layer_dim_dvs = 1
        
        # dvs super parameter  
        model = DEEPORYZA(input_dim = input_dim, hidden_dim = hidden_dim_dvs,layer_dim = layer_dim_dvs, 
                            output_dim = output_dim)
        model_ref = DEEPORYZA(input_dim = input_dim, hidden_dim = hidden_dim_dvs,layer_dim = layer_dim_dvs, 
                            output_dim = output_dim)
        
        model.to(device) 
     
        model_to_load = torch.load(os.path.join(model_path,trained_model_name))
        model.load_state_dict(model_to_load,strict=True)  

        model_ref.to(device) 
        model_ref.load_state_dict(model_to_load,strict=True)  
        
        criterion = nn.MSELoss()
        def mask_mse(pred,real,mask):
            weights =  [1,1,5,2,2,1,2]
            mse_loss = nn.MSELoss(reduction='none')
            loss = mse_loss(pred, real)
            # loss_dvs = layer(pred[:,:-1,0]-pred[:,1:,0]-0.00000).mean()
            # loss_mask = loss.masked_select(mask).mean()
            loss_split_mask = [loss[:,:,i].masked_select(mask[:,:,i]).mean()*weights[i] for i in range(loss.shape[2])]
            # np_mask = mask.clone().data.cpu().numpy()
            return sum(loss_split_mask),torch.Tensor(loss_split_mask)
        #%% -----------------------------------fit------------------------------------
    
        np_wea_fer_batchs, np_res_batchs, np_pre_batchs, np_obs_batchs, np_fit_batchs = [],[],[],[], []
        mode = "tes"
        for n,(x,y,o,f) in enumerate(tes_DataLoader):
            var_x, var_y, var_o, var_f = x.to(device), y.to(device), o.to(device), f.to(device)
            mask_res = var_y.ne(-10000)
            var_x = var_x.requires_grad_(True)
            var_out_all, aux_all = model(var_x[:,:,[1,2,3,7,8]],var_y)
            np_wea_fer = utils.unscalling(scal_type,utils.to_np(var_x),wea_fer_max,wea_fer_min,wea_fer_mean,wea_fer_std)
            np_res = utils.unscalling(scal_type,utils.to_np(var_y),res_max[obs_loc],res_min[obs_loc],res_mean[obs_loc],res_std[obs_loc])
            np_pre = utils.unscalling(scal_type,utils.to_np(var_out_all),res_max[obs_loc],res_min[obs_loc],res_mean[obs_loc],res_std[obs_loc])
            np_obs = utils.unscalling(scal_type,utils.to_np(var_o),res_max[obs_loc],res_min[obs_loc],res_mean[obs_loc],res_std[obs_loc])
            np_fit = utils.unscalling(scal_type,utils.to_np(var_f),res_max[obs_loc],res_min[obs_loc],res_mean[obs_loc],res_std[obs_loc])
                   
            a = res_min[obs_loc]
            b = res_max[obs_loc]
            np_wea_fer_batchs.append(np_wea_fer)
            np_res_batchs.append(np_res)
            np_pre_batchs.append(np_pre)
            np_obs_batchs.append(np_obs)
            np_fit_batchs.append(np_fit)
            mask_obs = var_o.ne(-10000)
            loss_res,loss_res_split = mask_mse(var_out_all, var_o, mask_obs)
            loss_ory,loss_res_split = mask_mse(var_y, var_o, mask_obs)
            grad = utils.gradients(var_out_all[:,110,-1],var_x)
            grad_np = utils.to_np(grad)
            
            print('tes: %.8f'%(loss_res.data))
            print('ory: %.8f'%(loss_ory.data))

        
        np_wea_fer_dataset = np.concatenate(np_wea_fer_batchs,0)
        np_res_dataset = np.concatenate(np_res_batchs,0)
        np_pre_dataset = np.concatenate(np_pre_batchs,0)
        np_obs_dataset = np.concatenate(np_obs_batchs,0)
        np_fit_dataset = np.concatenate(np_fit_batchs,0)
        # np_pre_ref_dataset = np.concatenate(np_pre_ref_batchs,0)
        np_res_points = np_res_dataset.reshape(-1,obs_dim)
        np_pre_points = np_pre_dataset.reshape(-1,obs_dim)
        np_obs_points = np_obs_dataset.reshape(-1,obs_dim)
        np_fit_points = np_fit_dataset.reshape(-1,obs_dim)
        
        np_pre_dataset_list.append(np_pre_dataset)
        np_pre_points_list.append(np_pre_points)
    np_pre_dataset_mean = np.stack(np_pre_dataset_list,0).mean(0)
    np_pre_points_mean = np.stack(np_pre_points_list,0).mean(0)
        
    
    np_pre_dataset_mean = np_pre_dataset_list[1]
    np_out_all_mean = utils.scalling(scal_type,np_pre_dataset_mean,res_max[obs_loc],res_min[obs_loc],res_mean[obs_loc],res_std[obs_loc])  
    var_out_all_mean = torch.tensor(np_out_all_mean, dtype=torch.float64).to(device)
    loss_ave,loss_res_split = mask_mse(var_out_all_mean, var_o, mask_obs)
    loss_ave = utils.to_np(loss_ave)
    
    
    alpha, fontsize = 1, 12
    i = 0
    r2_obs = []
    rmse_obs = []
    
    markersize = 1
    uplims = [2.3,7,4000,10000,10000,20000,10000]
    titles = ['生育期','植被面积指数','叶质量','茎质量','穗质量','地上生物量',"产量"]
    fig, axs = plt.subplots(dpi = 300,nrows=7, ncols=1, figsize=(2, 14))
    plt.subplots_adjust(left=0.1,
                        bottom=0.1,
                        right=0.8,
                        top=0.8,
                        wspace=0.1,
                        hspace=0.1)
    for i,(title,unit) in enumerate(zip(obs_name,units)):
        # fig = plt.figure(dpi = 300)
        

        x = np_obs_points[:,i]
        f = np_fit_points[:,i]
        y = np_pre_points[:,i]
        z = np_res_points[:,i]

        y = y[x>=0]
        z = z[x>=0]
        f = f[x>=0]
        x = x[x>=0]
        
        y = y
        x = x
        uplim = uplims[i]
        # if title=="WRR14": title = "YIELD"
        axs[i].plot(x, y, 'b.', color='black',markersize=markersize, alpha = alpha)
        axs[i].plot((0, uplim), (0, uplim), ls='--',c='k', label="1:1 line")
        axs[i].set_xticklabels([])
        axs[i].set_ylabel("%s(%s)"%(titles[i],units[i]))
        axs[i].set_yticklabels(axs[i].get_yticks(), rotation=90)
        axs[i].yaxis.set_major_formatter(utils.formatter)
        # axs[i].set_ylim(top=max_values[i])
        # plt.ylabel('Predicted (%s)'%unit,fontsize=fontsize)
        # plt.xlabel('Observed (%s)'%unit,fontsize=fontsize)
        # plt.tick_params(axis='both',labelsize=15)
        # plt.title(title,fontsize=fontsize)
        RMSE = 0
        R2= np.corrcoef(x, y)[0, 1] ** 2
        for tpt in range(0, len(x)):
            RMSE= RMSE + (x[tpt] - y[tpt]) ** 2
        RMSE = (RMSE / len(x)) ** 0.5
        axs[i].text(x=0.025 * uplim, y=0.78 * uplim, s='RMSE=' + str(RMSE)[:5],fontsize=fontsize,c="red")
        axs[i].text(x=0.025 * uplim, y=0.9 * uplim, s='R$^2$ = ' + str(R2)[:5],fontsize=fontsize,c="red")

        axs[i].axis('square')
        # plt.xlim([0, uplim])
        # plt.ylim([0, uplim])
        r2_obs.append(R2)
        rmse_obs.append(RMSE)
    save_dir = "figure/paper/scatter_CN"
    utils.find_or_make(save_dir)
    plt.savefig(os.path.join(save_dir,'2018-2018_ORYZA2000.png'), bbox_inches='tight')
    plt.show()
    plt.close(fig)            
    
    r2_list.append(r2_obs)
    rmse_list.append(rmse_obs)
    
    r2_array = np.array(r2_list)
    rmse_array = np.array(rmse_list)
    

    a_loss_rmse = np.concatenate(([loss_ave],rmse_array[0,1:]))[None,:]
    a_loss_r2 = np.concatenate(([loss_ave],r2_array[0,1:]))[None,:]

