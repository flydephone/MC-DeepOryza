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
from torch.autograd import Variable
from torch.utils.data import DataLoader

import datetime
import time
from models_aux.MyDataset import MyDataSet
from models_aux.NaiveLSTM import NaiveLSTM
from models_aux.DeepCGM_fast import DeepCGM
from models_aux.MCLSTM_fast import MCLSTM
import utils
from matplotlib.patches import Rectangle
from matplotlib.ticker import MaxNLocator
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

device = torch.device('cuda') if torch.cuda.is_available() else torch.device('cpu')


   
if __name__ == "__main__":
    # %%load base data
    seed=1
    model_dir_list = [
        ["2018","DeepCGM_spa_IM_CG_scratch"],
        ["2019","DeepCGM_spa_IM_CG_scratch"],
                  ]
    colors = ["cornflowerblue","lightcoral"]
    
    obs_name = ['DVS','PAI','WLV','WST','WSO','WAGT',"WRR14"]
    units = ['-',"m$^2$/m$^2$","kg/ha","kg/ha","kg/ha","kg/ha","kg/ha"]

    max_min = utils.pickle_load('format_dataset/max_min.pickle')
    obs_num = len(obs_name)
    obs_col_name = ['TIME','DVS','PAI','WLV','WST','WSO','WAGT',"WRR14"]
    obs_loc = [obs_col_name.index(name) for name in obs_name]
    res_max,res_min,par_max,par_min,wea_fer_max,wea_fer_min = max_min

    # %% creat instances from class_LSTM

    res_list = []
    pre_list = []
    obs_list = []
    wea_fer_list = []
    for model_dir_group in model_dir_list:
        tra_year = model_dir_group[0]
        model_dir = model_dir_group[1]
        sample_2018, sample_2019 = 65,40
        rea_ory_dataset,rea_par_dataset,rea_wea_fer_dataset,rea_spa_dataset,rea_int_dataset = utils.dataset_loader(data_source="format_dataset/real_%s"%(tra_year))
        if tra_year == "2018":
            tra_ory_dataset,tra_wea_fer_dataset,tra_spa_dataset,tra_int_dataset = rea_ory_dataset[:sample_2018],rea_wea_fer_dataset[:sample_2018],rea_spa_dataset[:sample_2018],rea_int_dataset[:sample_2018]
            tes_ory_dataset,tes_wea_fer_dataset,tes_spa_dataset,tes_int_dataset = rea_ory_dataset[sample_2018:],rea_wea_fer_dataset[sample_2018:],rea_spa_dataset[sample_2018:],rea_int_dataset[sample_2018:]
        elif tra_year == "2019":
            tes_ory_dataset,tes_wea_fer_dataset,tes_spa_dataset,tes_int_dataset = rea_ory_dataset[:sample_2018],rea_wea_fer_dataset[:sample_2018],rea_spa_dataset[:sample_2018],rea_int_dataset[:sample_2018]
            tra_ory_dataset,tra_wea_fer_dataset,tra_spa_dataset,tra_int_dataset = rea_ory_dataset[sample_2018:],rea_wea_fer_dataset[sample_2018:],rea_spa_dataset[sample_2018:],rea_int_dataset[sample_2018:]
        batch_size = 128
        tra_set = MyDataSet(obs_loc=obs_loc, ory=tra_ory_dataset, wea_fer=tra_wea_fer_dataset, spa=tra_spa_dataset, int_=tra_int_dataset, batch_size=batch_size)
        tra_DataLoader = DataLoader(tra_set, batch_size=batch_size, shuffle=False)
        tes_set = MyDataSet(obs_loc=obs_loc, ory=tes_ory_dataset, wea_fer=tes_wea_fer_dataset, spa=tes_spa_dataset, int_=tes_int_dataset, batch_size=batch_size)
        tes_DataLoader = DataLoader(tes_set, batch_size=batch_size, shuffle=False)


        model_list = os.listdir("model_weight/%s/"%model_dir) 
        model_list = [tpt for tpt in model_list if tra_year in tpt]
        
        model = model_list[seed]
        model_path = 'model_weight/%s/%s'%(model_dir,model)
        tra_loss = []
        tes_loss = []
        trained_model_names = os.listdir(model_path)
        for tpt in trained_model_names[:]:
            tra_loss += [float(tpt[:-4].split("_")[-3])]
            tes_loss += [float(tpt[:-4].split("_")[-1])]
        loss = np.array([tra_loss,tes_loss]).T
        min_indices = np.argmin(loss[:,0], axis=0)

        trained_model_name = trained_model_names[min_indices]
        # dvs super parameter  
        model_name = model_dir.split("_")[0]
        MODEL = eval(model_name)
        if "Naive" in model_name:
            model = MODEL()
        else:
            input_mask = "IM" in model_dir
            model = MODEL(input_mask = input_mask)
        model.to(device) 
        model_to_load = torch.load(os.path.join(model_path,trained_model_name))
        model.load_state_dict(model_to_load,strict=True)  

        #%% -----------------------------------fit------------------------------------
        np_wea_fer_batchs, np_res_batchs, np_pre_batchs, np_obs_batchs, np_fit_batchs = [],[],[],[], []
        mode = "tes"
        for n,(x,y,o,f) in enumerate(tes_DataLoader):
            var_x, var_y, var_o, var_f = x.to(device), y.to(device), o.to(device), f.to(device)
            var_out_all, aux_all = model(var_x[:,:,[1,2,3,7,8]],var_y)
            np_wea_fer = utils.unscalling(utils.to_np(var_x),wea_fer_max,wea_fer_min)
            np_res = utils.unscalling(utils.to_np(var_y),res_max[obs_loc],res_min[obs_loc])
            np_pre = utils.unscalling(utils.to_np(var_out_all),res_max[obs_loc],res_min[obs_loc])
            np_obs = utils.unscalling(utils.to_np(var_o),res_max[obs_loc],res_min[obs_loc])
            np_fit = utils.unscalling(utils.to_np(var_f),res_max[obs_loc],res_min[obs_loc])

            np_wea_fer_batchs.append(np_wea_fer)
            np_res_batchs.append(np_res)
            np_pre_batchs.append(np_pre)
            np_obs_batchs.append(np_obs)
            np_fit_batchs.append(np_fit)

        np_wea_fer_dataset = np.concatenate(np_wea_fer_batchs,0)
        np_res_dataset = np.concatenate(np_res_batchs,0)
        np_pre_dataset = np.concatenate(np_pre_batchs,0)
        np_obs_dataset = np.concatenate(np_obs_batchs,0)
        np_fit_dataset = np.concatenate(np_fit_batchs,0)
        # np_pre_ref_dataset = np.concatenate(np_pre_ref_batchs,0)
        np_res_points = np_res_dataset.reshape(-1,obs_num)
        np_pre_points = np_pre_dataset.reshape(-1,obs_num)
        np_obs_points = np_obs_dataset.reshape(-1,obs_num)
        np_fit_points = np_fit_dataset.reshape(-1,obs_num)
        res_list.append(np_res_dataset)
        pre_list.append(np_pre_dataset)
        obs_list.append(np_obs_dataset)
        wea_fer_list.append(np_wea_fer_dataset)

    # %% plot
    from matplotlib import rcParams
    from matplotlib.ticker import FuncFormatter, MaxNLocator
    
    config = {
        "font.size": 8,  # Font size
        'axes.unicode_minus': False,  # Handle minus signs
    }
    rcParams.update(config)
    
    
    nrows = 7
    ncols = 6
    fig, axs = plt.subplots(dpi=300, nrows=nrows, ncols=ncols, figsize=(10, 10))
    
    plt.subplots_adjust(left=0.1, bottom=0.1, right=0.8, top=0.9, wspace=0.1, hspace=0.1)
    
    max_values = [2.3, 8, 6000, 6000, 8000, 14000, 10000,100]
    # sample_loc = 10
    # Column titles
    col_titles = ["Zero","Moderate","High","Zero","Moderate","High"]
    # 2018-2019: -4, 4, 2
    # 2019-2018: -2, 0, 6
    sample_loc_list = [36,4,2,103,40,46]
    res_list = np.concatenate(res_list,0)
    pre_list = np.concatenate(pre_list,0)
    obs_list = np.concatenate(obs_list,0)
    wea_fer_list = np.concatenate(wea_fer_list,0)
    for i in range(nrows):
        for j in range(ncols):
            axs_ij = axs[i, j]
            sample_loc = sample_loc_list[j]
            day = wea_fer_list[sample_loc, :, 0]

            if i<6:
                res = res_list[sample_loc, :, i+1]
                obs = obs_list[sample_loc, :, i+1]
                pre = pre_list[sample_loc, :, i+1]
                axs_ij.scatter(day[(obs >= 0) * (day >= 0)], obs[(obs >= 0) * (day >= 0)], s=5, c='gray', label="observation")
                axs_ij.plot(day[(res >= 0) * (day >= 0)], res[(res >= 0) * (day >= 0)], c='gray', linewidth=1, label="ORYZA2000")
                axs_ij.plot(day[(res >= 0) * (day >= 0)], pre[(res >= 0) * (day >= 0)], c=colors[1], linewidth=0.75, alpha=1, label="DeepCGM")
        
                # Y-tick formatting
                axs_ij.set_yticklabels(axs_ij.get_yticks(), rotation=90, va="center")
                axs_ij.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{int(x):,}'))
                axs_ij.yaxis.set_major_locator(MaxNLocator(nbins=3))
                axs_ij.set_ylim(top=max_values[i+1])
            elif i==6:
                fer = wea_fer_list[sample_loc,:,-2]
                axs_ij.bar(day[(res>=0)*(day>=0)],fer[(res>=0)*(day>=0)],color="darkblue",width = 4)
                axs_ij.set_ylim(top=100)
                axs_ij.set_yticklabels(axs_ij.get_yticks(), rotation=90)
                axs_ij.yaxis.set_major_formatter(utils.formatter)

    
            if j == 0 and i<6:
                axs_ij.set_ylabel("%s(%s)" % (obs_name[i+1], units[i+1]))  # Add y-axis label
            elif j == 0 and i==6:
                axs_ij.set_ylabel("Nitrogen(kg/ha)")  # Add y-axis label
            else:
                axs_ij.set_yticklabels([])
    
            if i == nrows - 1:
                axs_ij.set_xlabel("Day of year")
            else:
                axs_ij.set_xticklabels([])
    
            axs_ij.text(0.03, 0.85, "(%s%d)" % (chr(97 + i+1-1), j+1), transform=axs_ij.transAxes, fontsize=10)
    # Add gray boxes and column titles
    for ax, col, j in zip(axs[0], col_titles, range(ncols)):
        # Calculate the coordinates of the box
        box_x0 = ax.get_position().x0  # Left boundary of the box
        box_width = ax.get_position().width  # Box width
        box_y0 = ax.get_position().y1  # Slightly above the top of the plot
        box_height = 0.03  # Height of the gray box
        if j==0:
            big_box_x0 = ax.get_position().x0
        if j==2:
            big_box_x1 = ax.get_position().x1
        if j==3:
            big_box_x2 = ax.get_position().x0
        if j==5:
            big_box_x3 = ax.get_position().x1

        # Draw the gray rectangle above the plot
        fig.patches.append(Rectangle((box_x0, box_y0), box_width, box_height,
                                      transform=fig.transFigure, facecolor="lightgray", edgecolor="black", zorder=3))

        # Add the title inside the gray box
        fig.text(box_x0 + box_width / 2, box_y0 + box_height / 2, col,
                 ha="center", va="center", fontsize=10, color="black", zorder=4)
    fig.patches.append(Rectangle((big_box_x0, box_y0+box_height), big_box_x1-big_box_x0, 0.03, transform=fig.transFigure, facecolor="lightgray", edgecolor="black", zorder=3))
    fig.patches.append(Rectangle((big_box_x2, box_y0+box_height), big_box_x3-big_box_x2, 0.03, transform=fig.transFigure, facecolor="lightgray", edgecolor="black", zorder=3))
    fig.text(big_box_x0 + (big_box_x1-big_box_x0) / 2, box_y0+box_height + 0.015, "2018-train 2019-test", ha="center", va="center", fontsize=10, color="black", zorder=4)
    fig.text(big_box_x2 + (big_box_x3-big_box_x2) / 2, box_y0+box_height + 0.015, "2019-train 2018-test", ha="center", va="center", fontsize=10, color="black", zorder=4)
    # fig.legend()
    legend_handles = [
        Line2D([0], [0], color='none', lw=0, marker='o', markersize=4,markerfacecolor='gray', markeredgewidth=0, label='Observation'),  # Solid point
        Line2D([0], [0], color='gray', lw=1, label='ORYZA2000'),        # Cyan line
        Line2D([0], [0], color="lightcoral", lw=1, label='DeepCGM'),    # Red line with CG loss
        Patch(facecolor='darkblue', label='Nitrogen Input')  # Bar legend (light blue color)
    ]
    plt.subplots_adjust(bottom=0.075)
    fig.legend(handles=legend_handles, loc='lower center', ncol=4, frameon=False)
    plt.rcParams['svg.fonttype'] = 'none'  # Ensure text is not converted to paths
    plt.savefig('figure/Fig.9 Crop growth process simulated by DeepCGM and ORYZA2000 from plots with different fertilization levels.svg', bbox_inches='tight',format="svg")
    plt.show()
    plt.close()


