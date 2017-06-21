clear

%% Define global parameters
PIECEWISE_CONSTANT_COMPENSATION_LOOKUP_TABLE_PATH = './piecewise_compensation_lookup.csv';
CUBIC_COMPENSATION_COEFFICIENT_FILE_PATH = './cubic_compensation_coefs.csv';

%% Parse in raw data
raw_filename = '../error_data/printer_accuracy_arjun.xlsx';
[~,~,headers] = xlsread(raw_filename, 'Z run charts', 'A1:D1','basic'); 
headers = replace(headers,' ','_'); %strip whitespace
headers = replace(headers,'%','Pct'); %strip special characters
[~,~,R] = xlsread(raw_filename, 'Z run charts', 'A2:D176','basic');
R = cell2table(R,'VariableNames',headers);
R.Measured_Length = R.Nominal_Length + R.Raw_Deviation;

% correct for quantization error
D = table(changem(R.Nominal_Length,[30-20.1 60-20.1 99.9-20.1 180-20.1 240-20.1],[10 40 80 160 220]),'VariableNames',{'Nominal_Length'});
D.Measured_Length = R.Measured_Length;
D.Absolute_Error = D.Measured_Length - D.Nominal_Length;

%% Calculate Piecewise-Constant Error Model
% S = table(unique(D.Nominal_Length+20.1),'VariableNames',{'Nominal_Length'},'RowNames',cellstr(num2str(unique(D.Nominal_Length))));
% nom_length_group = findgroups(D.Nominal_Length);
% S.Mean_Measured_Height = splitapply(@mean,D.Measured_Height,nom_length_group);
S = table([20.1;30;60;99.9;180;240],'VariableNames',{'Target_Height'});
S.Mean_Measured_Height(S.Target_Height==20.1)= 20.1;
for i = 2:numel(S.Target_Height)
    S.Mean_Measured_Height(i) = 20.1 + mean(D.Measured_Length(D.Nominal_Length+20.1==S.Target_Height(i)));
end

% Calculate mean absolute error
S.Mean_Abs_Err = S.Mean_Measured_Height-S.Target_Height;

% Calculate total error in each block
S.Error_This_Block(1) = 0;
S.Num_Layers_This_Block(1) = 20.1/0.3;
for i = 2:size(S,1)
    S.Error_This_Block(i) = S.Mean_Abs_Err(i)-S.Mean_Abs_Err(i-1);
    S.Num_Layers_This_Block(i) = (S.Target_Height(i)-S.Target_Height(i-1))/0.3;
end
S.Error_Per_Layer_This_Block = S.Error_This_Block./S.Num_Layers_This_Block;

% Package piecewise constant error compensation data for export
O = nan(6,3); % columns: begin_build_height(exclusive, except for 0-20.1 block), end_build_height(inclusive), compensation to apply per layer(+ve = thicker layers)
O(1,1) = 0;
O(:,2) = S.Target_Height;
O(:,3) = -S.Error_Per_Layer_This_Block;
O(1,3) = 0;
for i = 2:size(O,1)
    O(i,1) = O(i-1,2);
end

csvwrite(PIECEWISE_CONSTANT_COMPENSATION_LOOKUP_TABLE_PATH,O) %write model to file

%% Calculate Cubic Error Model
D.Target_Height = D.Nominal_Length + 20.1;
D.Measured_Height = D.Measured_Length + 20.1;
lm_cubic = fitlm(D.Target_Height, D.Measured_Height, 'measured_height ~ target_height + target_height^2 + target_height^3', 'VarNames', {'target_height' 'measured_height'},'Intercept',true);
O_cubic= lm_cubic.Coefficients.Estimate;
