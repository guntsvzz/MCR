import sys
from tqdm.auto import tqdm
data_name = sys.argv[1]

meta_file = open('./raw_data/meta_{}.json'.format(data_name)).readlines()
out_file = open('./tmp/filtered_meta_{}.json'.format(data_name), 'w')

print("Filtering items with incomplete features...")

total_node_num = 0
feature_sets = [set() for _ in range(4)]

def is_float(s):
    try:
        float(s)
        return True
    except ValueError:
        return False

for eachline in tqdm(meta_file):
    data = eval(eachline)
    if len(data['category']) >= 4 and 'price' in data:
        cid1, cid2, cid3 = data['category'][1:4]
        
        # Replace '&amp;' with '&'
        if '&amp;' in cid2:
            cid2 = cid2.replace('&amp;', '&')
        if '&amp;' in cid3:
            cid3 = cid3.replace('&amp;', '&')          
        price = data['price']
        if price== "":
            continue
        if is_float(price[1:]):
            price = float(price[1:])
        else:
            continue
        features = [cid2, cid3, price]
        for i in range(len(features)):
            feature_sets[i].add(features[i])
        # out_file.write(eachline)
        # total_node_num += 1
        
        # Update data with modified cid2 and cid3
        data['category'][2] = cid2
        data['category'][3] = cid3
        
        # Write updated data to out_file
        out_file.write(str(data) + '\n')
        total_node_num += 1

print('Total node num is {}'.format(total_node_num))

