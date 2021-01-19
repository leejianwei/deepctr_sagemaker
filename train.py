import os
import argparse

import json
import pandas as pd
import tensorflow as tf
from sklearn.metrics import log_loss, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder, MinMaxScaler

from deepctr.models import *
from deepctr.feature_column import SparseFeat, DenseFeat, get_feature_names

from deepctr.estimator import *
from deepctr.estimator.inputs import input_fn_pandas


def get_integer_mapping(le):
    '''
    Return a dict mapping labels to their integer values from an SKlearn LabelEncoder
    le = a fitted SKlearn LabelEncoder
    '''
    res = {}
    for idx, val in enumerate(le.classes_):
        res.update({val:idx})
    return res


def main(model_dir, data_dir, train_steps, model_name, task, **kwargs):
    print(kwargs)
    data = pd.read_csv(os.path.join(data_dir, 'criteo_sample.txt'))

    sparse_features = ['C' + str(i) for i in range(1, 27)]
    dense_features = ['I' + str(i) for i in range(1, 14)]

    data[sparse_features] = data[sparse_features].fillna('-1', )
    data[dense_features] = data[dense_features].fillna(0, )
    target = ['label']

    # 1.Label Encoding for sparse features,and do simple Transformation for dense features
    feat_index_dict = {}
    for feat in sparse_features:
        lbe = LabelEncoder()
        data[feat] = lbe.fit_transform(data[feat])
        feat_index_dict.update({feat:get_integer_mapping(lbe)})
    
    # save category features index for serving stage
    with open(os.path.join(model_dir, "feat_index_dict.json"), 'w') as fo:
        json.dump(feat_index_dict, fo)

    # save min max value for each dense feature 
    s_max,s_min = data[dense_features].max(axis=0),data[dense_features].min(axis=0)
    pd.concat([s_max, s_min],keys=['max','min'],axis=1).to_csv(os.path.join(model_dir, 'max_min.txt'), sep='\t')

    mms = MinMaxScaler(feature_range=(0, 1))
    data[dense_features] = mms.fit_transform(data[dense_features])

    # 2.count #unique features for each sparse field,and record dense feature field name

    fixlen_feature_columns = [SparseFeat(feat, vocabulary_size=data[feat].nunique(),embedding_dim=4)
                           for i,feat in enumerate(sparse_features)] + [DenseFeat(feat, 1,)
                          for feat in dense_features]

    dnn_feature_columns = fixlen_feature_columns
    linear_feature_columns = fixlen_feature_columns

    feature_names = get_feature_names(linear_feature_columns + dnn_feature_columns)

    # 3.generate input data for model

    train, test = train_test_split(data, test_size=0.2, random_state=2020)
    train_model_input = {name:train[name] for name in feature_names}
    test_model_input = {name:test[name] for name in feature_names}

    # 4.Define Model,train,predict and evaluate
    if model_name == 'DeepFM':
        # model = DeepFM(linear_feature_columns, dnn_feature_columns, fm_group=kwargs['fm_group'], dnn_hidden_units=kwargs['dnn_hidden_units'], l2_reg_linear=kwargs['l2_reg_linear'], l2_reg_embedding=kwargs['l2_reg_embedding'], l2_reg_dnn=kwargs['l2_reg_dnn'], seed=kwargs['seed'], dnn_dropout=kwargs['dnn_dropout'], dnn_activation=kwargs['dnn_activation'], dnn_use_bn=kwargs['dnn_use_bn'], task=task)
        model = DeepFMEstimator(linear_feature_columns, dnn_feature_columns, fm_group=kwargs['fm_group'], dnn_hidden_units=kwargs['dnn_hidden_units'], l2_reg_linear=kwargs['l2_reg_linear'], l2_reg_embedding=kwargs['l2_reg_embedding'], l2_reg_dnn=kwargs['l2_reg_dnn'], seed=kwargs['seed'], dnn_dropout=kwargs['dnn_dropout'], dnn_activation=kwargs['dnn_activation'], dnn_use_bn=kwargs['dnn_use_bn'], task=task)
    elif model_name == 'FNN':
        model = FNN(linear_feature_columns, dnn_feature_columns, task=task)
    elif model_name == 'WDL':
        model = WDL(linear_feature_columns, dnn_feature_columns, task=task)
    elif model_name == 'MLR':
        model = MLR(linear_feature_columns, dnn_feature_columns, task=task)
    elif model_name == 'NFM':
        model = NFM(linear_feature_columns, dnn_feature_columns, task=task)
    elif model_name == 'DIN':
        model = DIN(linear_feature_columns, dnn_feature_columns, task=task)
    elif model_name == 'CCPM':
        model = CCPM(linear_feature_columns, dnn_feature_columns, task=task)
    elif model_name == 'PNN':
        model = PNN(linear_feature_columns, dnn_feature_columns, task=task)
    elif model_name == 'AFM':
        model = AFM(linear_feature_columns, dnn_feature_columns, task=task)
    elif model_name == 'DCN':
        model = DCN(linear_feature_columns, dnn_feature_columns, task=task)
    elif model_name == 'DIEN':
        model = DIEN(linear_feature_columns, dnn_feature_columns, task=task)
    elif model_name == 'DSIN':
        model = DSIN(linear_feature_columns, dnn_feature_columns, task=task)
    elif model_name == 'xDeepFM':
        model = xDeepFM(linear_feature_columns, dnn_feature_columns, task=task)
    elif model_name == 'AutoInt':
        model = AutoInt(linear_feature_columns, dnn_feature_columns, task=task)
    elif model_name == 'ONN':
        model = ONN(linear_feature_columns, dnn_feature_columns, task=task)
    elif model_name == 'FGCNN':
        model = FGCNN(linear_feature_columns, dnn_feature_columns, task=task)
    elif model_name == 'FiBiNET':
        model = FiBiNET(linear_feature_columns, dnn_feature_columns, task=task)
    elif model_name == 'FLEN':
        model = FLEN(linear_feature_columns, dnn_feature_columns, task=task)
    else:
        print(model_name+' is not supported now.')
        return
    
    gpus = int(os.getenv('SM_NUM_GPUS', '0'))
    print('gpus:', gpus)
    if gpus > 1:
        from tensorflow.keras.utils import multi_gpu_model
        model = multi_gpu_model(model, gpus=gpus)
    
    model.compile("adam", "binary_crossentropy",
                  metrics=['binary_crossentropy'], )

    history = model.fit(train_model_input, train[target].values,
                        batch_size=256, epochs=train_steps, verbose=2, validation_split=0.2, )
    pred_ans = model.predict(test_model_input, batch_size=256)
    try:
        print("test LogLoss", round(log_loss(test[target].values, pred_ans), 4))
    except Exception as e:
        print(e)
    try:
        print("test AUC", round(roc_auc_score(test[target].values, pred_ans), 4))
    except Exception as e:
        print(e)
    
    # model.save_weights(os.path.join(model_dir, 'DeepFM_w.h5'))

    # 5.saved Model by build_raw_serving_input ,generate model in export_path
    def serving_input_receiver_fn():
        feature_map = {}
        for i in range(len(sparse_features)):
            feature_map[sparse_features[i]] = tf.placeholder(tf.int32,shape=(None, ),name='{}'.format(sparse_features[i]))
        for i in range(len(dense_features)):
            feature_map[dense_features[i]] = tf.placeholder(tf.float32,shape=(None, ),name='{}'.format(dense_features[i]))
        return tf.estimator.export.build_raw_serving_input_receiver_fn(feature_map)
        
    model.export_savedmodel(export_dir_base=os.path.join(model_dir, 'export/Servo'), serving_input_receiver_fn=serving_input_receiver_fn())


if __name__ == "__main__":
    args_parser = argparse.ArgumentParser()
    # For more information:
    # https://docs.aws.amazon.com/sagemaker/latest/dg/your-algorithms-training-algo.html
    args_parser.add_argument(
        '--data_dir',
        default='/opt/ml/input/data/training',
        type=str,
        help='The directory where the input data is stored. Default: /opt/ml/input/data/training. This '
             'directory corresponds to the SageMaker channel named \'training\', which was specified when creating '
             'our training job on SageMaker')

    # For more information:
    # https://docs.aws.amazon.com/sagemaker/latest/dg/your-algorithms-inference-code.html
    args_parser.add_argument(
        '--model_dir',
        default='/opt/ml/model',
        type=str,
        help='The directory where the model will be stored. Default: /opt/ml/model. This directory should contain all '
             'final model artifacts as Amazon SageMaker copies all data within this directory as a single object in '
             'compressed tar format.')

    args_parser.add_argument(
        '--train_steps',
        type=int,
        default=100,
        help='The number of steps to use for training.')
    
    args_parser.add_argument(
        '--model_name',
        default='DeepFM',
        type=str,
        help='Models: CCPM, FNN, PNN, WDL, DeepFM, MLR, NFM, AFM, DCN, DCNMix, DIN, DIEN, DSIN, xDeepFM, AutoInt, ONN, FGCNN, FiBiNET, FLEN.')
    
    args_parser.add_argument(
        '--task',
        default='binary',
        type=str,
        help='"binary" for binary logloss or "regression" for regression loss')
    
    # hyperparameters
    args_parser.add_argument(
        '--fm_group',
        default=['default_group'],
        type=list,
        help='group_name of features that will be used to do feature interactions.')
    args_parser.add_argument(
        '--dnn_hidden_units',
        default=(128, 128),
        type=list,
        help='list of positive integer or empty list, the layer number and units in each layer of DNN')
    args_parser.add_argument(
        '--cross_num',
        default=2,
        type=int,
        help='positive integet,cross layer number')
    args_parser.add_argument(
        '--cross_parameterization',
        default='vector',
        type=str,
        help='"vector" or "matrix", how to parameterize the cross network.')
    args_parser.add_argument(
        '--l2_reg_cross',
        default=1e-5,
        type=float,
        help='L2 regularizer strength applied to cross net')
    args_parser.add_argument(
        '--l2_reg_linear',
        default=1e-05,
        type=float,
        help='L2 regularizer strength applied to linear part')
    args_parser.add_argument(
        '--l2_reg_embedding',
        default=1e-05,
        type=float,
        help='L2 regularizer strength applied to embedding vector')
    args_parser.add_argument(
        '--l2_reg_dnn',
        default=0,
        type=float,
        help='L2 regularizer strength applied to DNN')
    args_parser.add_argument(
        '--seed',
        default=1024,
        type=int,
        help='to use as random seed.')
    args_parser.add_argument(
        '--dnn_dropout',
        default=0,
        type=float,
        help='float in [0,1), the probability we will drop out a given DNN coordinate.')
    args_parser.add_argument(
        '--dnn_activation',
        default='relu',
        type=str,
        help='Activation function to use in DNN')
    args_parser.add_argument(
        '--dnn_use_bn',
        default=False,
        type=bool,
        help='Whether use BatchNormalization before activation or not in DNN')
    args_parser.add_argument(
        '--low_rank',
        default=32,
        type=int,
        help='Positive integer, dimensionality of low-rank sapce.')
    args_parser.add_argument(
        '--num_experts',
        default=4,
        type=int,
        help='Positive integer, number of experts.')
    
    args = args_parser.parse_args()
    main(**vars(args))
    